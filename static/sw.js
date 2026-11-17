self.addEventListener("push", function (event) {
    let data = {};
    try {
        data = event.data.json();
    } catch (error) {
        data = {
            title: "Nueva notificación",
            body: event.data ? event.data.text() : "Tienes una nueva alerta."
        };
    }

    const title = data.title || "Nueva notificación";

    const options = {
        body: data.body || "Tienes una nueva alerta.",
        icon: data.icon || "/static/icono.jpg",
        badge: data.badge || "/static/icono.jpg",
        tag: data.tag || undefined,
        renotify: data.renotify !== undefined ? data.renotify : true,
        data: {
            url: data.url || "/detecciones"
        }
    };

    event.waitUntil(
        self.registration.showNotification(title, options)
    );
});

self.addEventListener("notificationclick", function (event) {
    event.notification.close();
    const targetUrl = (event.notification.data && event.notification.data.url) ? event.notification.data.url : "/detecciones";

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
