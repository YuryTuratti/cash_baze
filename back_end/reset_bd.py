import psycopg2
import os
from dotenv import load_dotenv

# Carrega as mesmas senhas do seu .env
load_dotenv()

def limpar_tudo():
    try:
        conexao = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            database=os.getenv("DB_NAME", "gasto_yury"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASS", ""),
            port=int(os.getenv("DB_PORT", 5432))
        )
        cursor = conexao.cursor()

        print("🧹 Passando a vassoura no banco de dados...")
        
        # O comando CASCADE força a deleção de tudo que estiver amarrado a essas tabelas
        cursor.execute("DROP TABLE IF EXISTS transacoes CASCADE;")
        cursor.execute("DROP TABLE IF EXISTS limites CASCADE;")
        cursor.execute("DROP TABLE IF EXISTS despesas_fixas CASCADE;")
        cursor.execute("DROP TABLE IF EXISTS usuarios CASCADE;")
        
        conexao.commit()
        cursor.close()
        conexao.close()
        
        print("✅ Banco de dados aniquilado com sucesso!")
        print("💡 As tabelas serão recriadas zeradas assim que você ligar o uvicorn.")
        
    except Exception as e:
        print(f"❌ Erro ao limpar o banco: {e}")

if __name__ == "__main__":
    print("⚠️ ATENÇÃO: Isso vai apagar TODAS as transações, limites e o seu LOGIN.")
    resposta = input("Tem certeza absoluta que deseja continuar? (s/n): ")
    
    if resposta.lower() == 's':
        limpar_tudo()
    else:
        print("🛑 Operação cancelada. Nada foi apagado.")