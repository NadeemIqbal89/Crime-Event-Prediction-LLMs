const whatsappManager = require('./WhatsAppManager.js');
const { MessageMedia } = require('whatsapp-web.js');
const fs = require('fs');
const path = require('path');

class ImageHandler {
    async sendImage(to, imagePath, caption = '') {
        try {
            const client = await whatsappManager.initialize();
            
            if (!fs.existsSync(imagePath)) {
                throw new Error('Image file not found');
            }

            const media = MessageMedia.fromFilePath(imagePath);
            return await client.sendMessage(to, media, { caption });
        } catch (error) {
            console.error('Error sending image:', error);
            throw error;
        }
    }

    async sendImageFromBuffer(to, imageBuffer, filename, caption = '') {
        try {
            const client = await whatsappManager.initialize();
            
            const media = new MessageMedia('image/jpeg', imageBuffer.toString('base64'), filename);
            return await client.sendMessage(to, media, { caption });
        } catch (error) {
            console.error('Error sending image from buffer:', error);
            throw error;
        }
    }

    async sendImageFromUrl(to, imageUrl, caption = '') {
        try {
            const client = await whatsappManager.initialize();
            
            const response = await fetch(imageUrl);
            const imageBuffer = await response.arrayBuffer();
            const media = new MessageMedia('image/jpeg', Buffer.from(imageBuffer).toString('base64'));
            
            return await client.sendMessage(to, media, { caption });
        } catch (error) {
            console.error('Error sending image from URL:', error);
            throw error;
        }
    }

    async downloadImage(message) {
        try {
            if (!message.hasMedia) {
                throw new Error('Message does not contain media');
            }

            const media = await message.downloadMedia();
            const buffer = Buffer.from(media.data, 'base64');
            
            const filename = `image_${Date.now()}.${media.mimetype.split('/')[1]}`;
            const filepath = path.join(__dirname, 'downloads', filename);
            
            if (!fs.existsSync(path.dirname(filepath))) {
                fs.mkdirSync(path.dirname(filepath), { recursive: true });
            }
            
            fs.writeFileSync(filepath, buffer);
            return { filepath, filename, mimetype: media.mimetype };
        } catch (error) {
            console.error('Error downloading image:', error);
            throw error;
        }
    }
}

const imageHandler = new ImageHandler();
module.exports = imageHandler;
