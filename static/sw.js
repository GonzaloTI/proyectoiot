// Service Worker para el sistema de alertas y Notificaciones Web Push
self.addEventListener("install", function (event) {
    // Forzar activación inmediata sin esperar a que se cierren pestañas abiertas
    self.skipWaiting();
});

self.addEventListener("activate", function (event) {
    // Tomar control de todas las ventanas abiertas de inmediato
    event.waitUntil(self.clients.claim());
});

self.addEventListener("push", function (event) {
    let data = {};
    try {
        data = event.data ? event.data.json() : {};
    } catch (error) {
        data = {
            title: "🔔 Proyecto IoT",
            body: event.data ? event.data.text() : "Tienes una nueva alerta del sistema."
        };
    }

    const title = data.title || "🔔 Proyecto IoT";

    const options = {
        body: data.body || "Tienes una nueva alerta del sistema.",
        icon: data.icon || "/static/icono.jpg",
        badge: data.badge || "/static/icono.jpg",
        vibrate: [200, 100, 200],
        data: {
            url: data.url || "/"
        }
    };

    // La especificación Web Notifications exige que renotify SOLO sea true si existe un tag no vacío
    const rawTag = (data.tag !== undefined && data.tag !== null) ? String(data.tag).trim() : "";
    if (rawTag.length > 0) {
        options.tag = rawTag;
        options.renotify = (data.renotify !== undefined) ? Boolean(data.renotify) : true;
    } else {
        // Si no hay tag, bajo ninguna circunstancia se debe incluir renotify
        delete options.renotify;
        delete options.tag;
    }

    event.waitUntil(
        self.registration.showNotification(title, options).catch(function (err) {
            console.error("Error al mostrar notificación con opciones completas:", err);
            // Fallback seguro sin tag ni opciones adicionales para garantizar que siempre se muestre
            return self.registration.showNotification(title, {
                body: options.body,
                icon: options.icon
            });
        })
    );
});

self.addEventListener("notificationclick", function (event) {
    event.notification.close();
    const targetUrl = (event.notification.data && event.notification.data.url) ? event.notification.data.url : "/";

    event.waitUntil(
        clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (clientList) {
            for (let i = 0; i < clientList.length; i++) {
                let client = clientList[i];
                if (client.url.includes(targetUrl) && "focus" in client) {
                    return client.focus();
                }
            }
            if (clients.openWindow) {
                return clients.openWindow(targetUrl);
            }
        })
    );
});
