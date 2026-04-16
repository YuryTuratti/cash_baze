from fastapi import FastAPI, Request, Depends, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
from typing import Optional
import psycopg2
import os
import logging
import jwt
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from passlib.context import CryptContext # CORREÇÃO 1: Import da segurança Bcrypt

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
load_dotenv()
app = FastAPI()

# CORREÇÃO 2: allow_credentials=False para não travar o servidor
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=False,
    allow_methods=["*"], allow_headers=["*"],
)

SECRET_KEY = os.getenv("JWT_SECRET")

# Trava de segurança: se a VPS não tiver a senha, o app nem liga.
if not SECRET_KEY:
    raise ValueError("ERRO FATAL: A variável JWT_SECRET não foi configurada no arquivo .env!")

ALGORITHM = "HS256"

security = HTTPBearer()

# Configuração do Bcrypt (Senhas Blindadas)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- MODELOS ---
class UsuarioRegistro(BaseModel):
    nome: str
    email: str 
    senha: str
    salario: float = 0.0
    dia_pagamento: int = 5

class UsuarioConfig(BaseModel):
    salario: float
    dia_pagamento: int

class UsuarioLogin(BaseModel):
    email: str 
    senha: str

class TransacaoIn(BaseModel):
    tipo: str
    valor: float
    categoria: str
    descricao: str = ""

class LimiteIn(BaseModel):
    categoria: str
    limite_valor: float

class DespesaFixaIn(BaseModel):
    descricao: str
    valor: float
    dia_vencimento: int
    categoria: str = "Outros"

# --- BANCO DE DADOS ---
def conectar_banco():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        database=os.getenv("DB_NAME", "gasto_yury"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASS", ""),
        port=int(os.getenv("DB_PORT", 5432))
    )

def processar_despesas_fixas():
    dia_atual = datetime.now().day
    try:
        conexao = conectar_banco()
        cursor = conexao.cursor()
        try:
            cursor.execute("SELECT usuario_id, descricao, valor, categoria FROM despesas_fixas WHERE dia_vencimento = %s", (dia_atual,))
            contas = cursor.fetchall()
            for c in contas:
                u_id, desc, valor, cat = c
                desc_auto = f"{desc} (Automático)"
                cursor.execute("SELECT id FROM transacoes WHERE usuario_id=%s AND descricao=%s AND DATE(data_registro)=CURRENT_DATE", (u_id, desc_auto))
                if not cursor.fetchone():
                    cursor.execute("INSERT INTO transacoes (usuario_id, tipo, valor, categoria, descricao) VALUES (%s, 'saida', %s, %s, %s)", (u_id, valor, cat, desc_auto))
            conexao.commit()
        finally:
            cursor.close()
            conexao.close()
    except Exception as e: 
        logging.error(f"Erro Robô: {e}")

agendador = BackgroundScheduler()

@app.on_event("startup")
def iniciar_sistema():
    try:
        conexao = conectar_banco()
        cursor = conexao.cursor()
        try:
            cursor.execute('''CREATE TABLE IF NOT EXISTS usuarios (
                id SERIAL PRIMARY KEY, 
                nome VARCHAR(100), 
                email VARCHAR(255) UNIQUE, 
                senha_hash VARCHAR(255), 
                salario NUMERIC(10,2) DEFAULT 0.0, 
                dia_pagamento INTEGER DEFAULT 5)''')
            
            cursor.execute('''CREATE TABLE IF NOT EXISTS transacoes (id SERIAL PRIMARY KEY, usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE, tipo VARCHAR(50), valor NUMERIC(10,2), categoria VARCHAR(100), descricao TEXT, data_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS limites (id SERIAL PRIMARY KEY, usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE, categoria VARCHAR(100), limite_valor NUMERIC(10,2), UNIQUE(usuario_id, categoria))''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS despesas_fixas (id SERIAL PRIMARY KEY, usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE, descricao VARCHAR(255), valor NUMERIC(10,2), categoria VARCHAR(100), dia_vencimento INTEGER)''')
            conexao.commit()
        finally:
            cursor.close()
            conexao.close()
        
        if not agendador.get_jobs():
            agendador.add_job(processar_despesas_fixas, 'cron', hour=0, minute=1)
            agendador.start()
        logging.info("✅ Sistema Iniciado com Segurança e Prevenção de Vazamento de Memória")
    except Exception as e: 
        logging.error(f"Erro Startup: {e}")

# --- UTILITÁRIOS ---
def gerar_hash_senha(senha: str): 
    return pwd_context.hash(senha) # CORREÇÃO: Usando Bcrypt

def verificar_senha(senha_plana: str, senha_hash: str):
    return pwd_context.verify(senha_plana, senha_hash) # CORREÇÃO: Verificador do Bcrypt

def criar_token(data: dict):
    to_encode = data.copy()
    to_encode.update({"exp": datetime.utcnow() + timedelta(days=7)})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def obter_usuario_atual(credentials: HTTPAuthorizationCredentials = Security(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        return int(payload.get("sub"))
    except: 
        raise HTTPException(status_code=401, detail="Sessão expirada")

# --- ROTAS ---
# CORREÇÃO 3: Todas as rotas agora usam try/finally para garantir o fechamento do banco

@app.post("/api/auth/registrar")
def registrar(user: UsuarioRegistro):
    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        cursor.execute(
            "INSERT INTO usuarios (nome, email, senha_hash, salario, dia_pagamento) VALUES (%s, %s, %s, %s, %s)", 
            (user.nome, user.email.lower().strip(), gerar_hash_senha(user.senha), user.salario, user.dia_pagamento)
        )
        conexao.commit()
        return {"ok": True}
    finally:
        cursor.close()
        conexao.close()

@app.post("/api/auth/login")
def login(user: UsuarioLogin):
    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        cursor.execute("SELECT id, nome, senha_hash FROM usuarios WHERE email = %s", (user.email.lower().strip(),))
        res = cursor.fetchone()
        
        # MUDANÇA: Usa a função verificar_senha do Bcrypt
        if not res or not verificar_senha(user.senha, res[2]): 
            raise HTTPException(status_code=401, detail="Email ou senha incorretos")
            
        return {"access_token": criar_token({"sub": str(res[0]), "nome": res[1]}), "nome": res[1]}
    finally:
        cursor.close()
        conexao.close()

@app.get("/api/usuario")
def get_usuario(u_id: int = Depends(obter_usuario_atual)):
    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        cursor.execute("SELECT salario, dia_pagamento FROM usuarios WHERE id = %s", (u_id,))
        res = cursor.fetchone()
        if not res: raise HTTPException(status_code=401)
        return {"salario": float(res[0] or 0), "dia_pagamento": res[1] or 5}
    finally:
        cursor.close()
        conexao.close()

@app.put("/api/usuario")
def update_usuario(dados: UsuarioConfig, u_id: int = Depends(obter_usuario_atual)):
    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        cursor.execute("UPDATE usuarios SET salario = %s, dia_pagamento = %s WHERE id = %s", (dados.salario, dados.dia_pagamento, u_id))
        conexao.commit()
        return {"ok": True}
    finally:
        cursor.close()
        conexao.close()

@app.post("/api/transacoes")
def criar_transacao(t: TransacaoIn, u_id: int = Depends(obter_usuario_atual)):
    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        cursor.execute("INSERT INTO transacoes (usuario_id, tipo, valor, categoria, descricao) VALUES (%s, %s, %s, %s, %s)", (u_id, t.tipo, t.valor, t.categoria, t.descricao))
        conexao.commit()
        return {"ok": True}
    finally:
        cursor.close()
        conexao.close()

@app.get("/api/transacoes/todas")
def get_todas(mes: int, ano: int, u_id: int = Depends(obter_usuario_atual)):
    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        cursor.execute("SELECT id, categoria, valor, descricao, data_registro, tipo FROM transacoes WHERE usuario_id=%s AND EXTRACT(MONTH FROM data_registro)=%s AND EXTRACT(YEAR FROM data_registro)=%s ORDER BY data_registro DESC", (u_id, mes, ano))
        res = cursor.fetchall()
        return [{"id": r[0], "categoria": r[1], "valor": float(r[2]), "desc": r[3], "data": r[4].strftime("%d/%m/%Y"), "tipo": r[5]} for r in res]
    finally:
        cursor.close()
        conexao.close()

@app.delete("/api/transacoes/{t_id}")
def deletar(t_id: int, u_id: int = Depends(obter_usuario_atual)):
    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        cursor.execute("DELETE FROM transacoes WHERE id=%s AND usuario_id=%s", (t_id, u_id))
        conexao.commit()
        return {"ok": True}
    finally:
        cursor.close()
        conexao.close()

@app.get("/api/resumo")
def get_resumo(mes: int, ano: int, u_id: int = Depends(obter_usuario_atual)):
    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        cursor.execute("SELECT COALESCE(SUM(valor),0) FROM transacoes WHERE tipo='entrada' AND usuario_id=%s AND EXTRACT(MONTH FROM data_registro)=%s AND EXTRACT(YEAR FROM data_registro)=%s", (u_id, mes, ano))
        ent = cursor.fetchone()[0]
        cursor.execute("SELECT COALESCE(SUM(valor),0) FROM transacoes WHERE tipo='saida' AND usuario_id=%s AND EXTRACT(MONTH FROM data_registro)=%s AND EXTRACT(YEAR FROM data_registro)=%s", (u_id, mes, ano))
        sai = cursor.fetchone()[0]
        return {"saldo_total": f"{ent:,.2f}", "gasto_mensal": f"{sai:,.2f}"}
    finally:
        cursor.close()
        conexao.close()

@app.get("/api/armazenamento")
def get_armazenamento(mes: int, ano: int, u_id: int = Depends(obter_usuario_atual)):
    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        cursor.execute("SELECT categoria, SUM(valor) FROM transacoes WHERE usuario_id=%s AND tipo='saida' AND EXTRACT(MONTH FROM data_registro)=%s AND EXTRACT(YEAR FROM data_registro)=%s GROUP BY 1 LIMIT 5", (u_id, mes, ano))
        res = cursor.fetchall()
        return {"tipos": [r[0] for r in res] or ["Vazio"], "valores": [float(r[1]) for r in res] or [0]}
    finally:
        cursor.close()
        conexao.close()

@app.get("/api/analise/comparativo")
def get_comparativo(u_id: int = Depends(obter_usuario_atual)):
    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        cursor.execute("SELECT TO_CHAR(data_registro, 'Mon'), SUM(CASE WHEN tipo='entrada' THEN valor ELSE 0 END), SUM(CASE WHEN tipo='saida' THEN valor ELSE 0 END) FROM transacoes WHERE usuario_id=%s AND data_registro >= NOW() - INTERVAL '6 months' GROUP BY 1, DATE_TRUNC('month', data_registro) ORDER BY DATE_TRUNC('month', data_registro)", (u_id,))
        res = cursor.fetchall()
        return {"labels": [r[0] for r in res], "entradas": [float(r[1]) for r in res], "saidas": [float(r[2]) for r in res]}
    finally:
        cursor.close()
        conexao.close()

@app.get("/api/gastos-diarios")
def get_gastos_diarios(mes: int, ano: int, u_id: int = Depends(obter_usuario_atual)):
    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        cursor.execute("SELECT TO_CHAR(data_registro, 'DD Mon') as dia, SUM(valor) FROM transacoes WHERE tipo = 'saida' AND usuario_id = %s AND EXTRACT(MONTH FROM data_registro)=%s AND EXTRACT(YEAR FROM data_registro)=%s GROUP BY DATE_TRUNC('day', data_registro), 1 ORDER BY DATE_TRUNC('day', data_registro)", (u_id, mes, ano))
        res = cursor.fetchall()
        return {"dias": [r[0] for r in res] or ["Sem dados"], "valores": [float(r[1]) for r in res] or [0]}
    finally:
        cursor.close()
        conexao.close()

@app.get("/api/limites")
def get_limites(u_id: int = Depends(obter_usuario_atual)):
    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        cursor.execute("SELECT categoria, limite_valor FROM limites WHERE usuario_id=%s", (u_id,))
        res = cursor.fetchall()
        return {r[0]: float(r[1]) for r in res}
    finally:
        cursor.close()
        conexao.close()

@app.post("/api/limites")
def set_limite(l: LimiteIn, u_id: int = Depends(obter_usuario_atual)):
    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        cursor.execute("INSERT INTO limites (usuario_id, categoria, limite_valor) VALUES (%s, %s, %s) ON CONFLICT (usuario_id, categoria) DO UPDATE SET limite_valor = EXCLUDED.limite_valor", (u_id, l.categoria, l.limite_valor))
        conexao.commit()
        return {"ok": True}
    finally:
        cursor.close()
        conexao.close()

@app.get("/api/despesas-fixas")
def get_despesas_fixas(u_id: int = Depends(obter_usuario_atual)):
    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        cursor.execute("SELECT id, descricao, valor, dia_vencimento, categoria FROM despesas_fixas WHERE usuario_id=%s ORDER BY dia_vencimento ASC", (u_id,))
        res = cursor.fetchall()
        return [{"id": r[0], "desc": r[1], "valor": float(r[2]), "dia": r[3], "categoria": r[4]} for r in res]
    finally:
        cursor.close()
        conexao.close()

@app.post("/api/despesas-fixas")
def set_despesa_fixa(df: DespesaFixaIn, u_id: int = Depends(obter_usuario_atual)):
    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        cursor.execute("INSERT INTO despesas_fixas (usuario_id, descricao, valor, dia_vencimento, categoria) VALUES (%s, %s, %s, %s, %s)", (u_id, df.descricao, df.valor, df.dia_vencimento, df.categoria))
        conexao.commit()
        return {"ok": True}
    finally:
        cursor.close()
        conexao.close()

@app.delete("/api/despesas-fixas/{f_id}")
def deletar_despesa_fixa(f_id: int, u_id: int = Depends(obter_usuario_atual)):
    conexao = conectar_banco()
    cursor = conexao.cursor()
    try:
        cursor.execute("DELETE FROM despesas_fixas WHERE id=%s AND usuario_id=%s", (f_id, u_id))
        conexao.commit()
        return {"ok": True}
    finally:
        cursor.close()
        conexao.close()