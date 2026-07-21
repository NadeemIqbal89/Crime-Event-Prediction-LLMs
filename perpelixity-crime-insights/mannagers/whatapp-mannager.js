const { Client } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');

class WhatsAppManager {
    constructor() {
        this.client = null;
        this.isInitialized = false;
    }

    async initialize() {
        if (this.isInitialized) {
            return this.client;
        }

        this.client = new Client();
        
        this.client.on('ready', () => {
            console.log('Client is ready!');
        });

        this.client.on('qr', qr => {
            qrcode.generate(qr, {small: true});
        });

        this.client.on('message_create', message => {
            console.log(message);
            if (message.body === '!ping') {
                this.client.sendMessage(message.from, 'pong');
            }
        });

        await this.client.initialize();
        this.isInitialized = true;
        return this.client;
    }

    getClient() {
        if (!this.isInitialized) {
            throw new Error('WhatsApp client not initialized. Call initialize() first.');
        }
        return this.client;
    }

    async sendMessage(to, message) {
        const client = await this.initialize();
        return client.sendMessage(to, message);
    }
}

const whatsappManager = new WhatsAppManager();

module.exports = whatsappManager;
