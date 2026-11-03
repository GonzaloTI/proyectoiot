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
        icon: "/static/icono.jpg",
        badge: "/static/icono.jpg"
    };

    event.waitUntil(
        self.registration.showNotification(title, options)
    );
});

self.addEventListener("notificationclick", function (event) {
    event.notification.close();
    event.waitUntil(
        clients.openWindow("/")
    );
});
