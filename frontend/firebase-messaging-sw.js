// Importa o Firebase no Worker
importScripts('https://www.gstatic.com/firebasejs/9.23.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/9.23.0/firebase-messaging-compat.js');

// A MESMA configuração do seu HTML
firebase.initializeApp({
    apiKey: "SUA_API_KEY_DO_FIREBASE",
    authDomain: "SEU_PROJETO.firebaseapp.com",
    projectId: "SEU_PROJETO",
    storageBucket: "SEU_PROJETO.appspot.com",
    messagingSenderId: "SEU_SENDER_ID",
    appId: "SEU_APP_ID"
});

const messaging = firebase.messaging();

// Ouve os disparos em segundo plano
messaging.onBackgroundMessage(function(payload) {
    console.log('[firebase-messaging-sw.js] Notificação recebida em background.', payload);

    // Usa os dados que o seu PHP mandou!
    // (A sua função send_to_token manda os dados em title, body, etc)
    const notificationTitle = payload.data.title || payload.notification?.title || 'Aviso do Gasto Yury';
    const notificationOptions = {
        body: payload.data.body || payload.notification?.body || 'Você tem uma nova mensagem.',
        icon: 'https://cdn-icons-png.flaticon.com/512/2933/2933116.png',
        badge: 'https://cdn-icons-png.flaticon.com/512/2933/2933116.png',
        data: { url: payload.data.url || '/' }
    };

    return self.registration.showNotification(notificationTitle, notificationOptions);
});

// Ação de clique na notificação
self.addEventListener('notificationclick', function(event) {
    event.notification.close();
    if (event.notification.data && event.notification.data.url) {
        event.waitUntil(clients.openWindow(event.notification.data.url));
    } else {
        event.waitUntil(clients.openWindow('/'));
    }
});