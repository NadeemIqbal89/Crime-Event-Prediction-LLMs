const whatsappManager = require('./WhatsAppManager.js');
const { MessageMedia } = require('whatsapp-web.js');
const fs = require('fs');
const path = require('path');

class MessageHandler {
    async sendText(to, text) {
        try {
            const client = await whatsappManager.initialize();
            return await client.sendMessage(to, text);
        } catch (error) {
            console.error('Error sending text message:', error);
            throw error;
        }
    }

    async sendVoiceMessage(to, audioPath, caption = '') {
        try {
            const client = await whatsappManager.initialize();
            
            if (!fs.existsSync(audioPath)) {
                throw new Error('Audio file not found');
            }

            const media = MessageMedia.fromFilePath(audioPath);
            return await client.sendMessage(to, media, { 
                sendAudioAsVoice: true,
                caption 
            });
        } catch (error) {
            console.error('Error sending voice message:', error);
            throw error;
        }
    }

    async sendVoiceFromBuffer(to, audioBuffer, filename, caption = '') {
        try {
            const client = await whatsappManager.initialize();
            
            const media = new MessageMedia('audio/ogg', audioBuffer.toString('base64'), filename);
            return await client.sendMessage(to, media, { 
                sendAudioAsVoice: true,
                caption 
            });
        } catch (error) {
            console.error('Error sending voice from buffer:', error);
            throw error;
        }
    }

    async sendVoiceFromUrl(to, audioUrl, caption = '') {
        try {
            const client = await whatsappManager.initialize();
            
            const response = await fetch(audioUrl);
            const audioBuffer = await response.arrayBuffer();
            const media = new MessageMedia('audio/ogg', Buffer.from(audioBuffer).toString('base64'));
            
            return await client.sendMessage(to, media, { 
                sendAudioAsVoice: true,
                caption 
            });
        } catch (error) {
            console.error('Error sending voice from URL:', error);
            throw error;
        }
    }

    async sendBulkText(toList, text) {
        try {
            const client = await whatsappManager.initialize();
            const results = [];
            
            for (const to of toList) {
                try {
                    const result = await client.sendMessage(to, text);
                    results.push({ to, success: true, result });
                } catch (error) {
                    results.push({ to, success: false, error: error.message });
                }
            }
            
            return results;
        } catch (error) {
            console.error('Error sending bulk text messages:', error);
            throw error;
        }
    }

    async sendBulkVoice(toList, audioPath, caption = '') {
        try {
            const client = await whatsappManager.initialize();
            const results = [];
            
            if (!fs.existsSync(audioPath)) {
                throw new Error('Audio file not found');
            }

            const media = MessageMedia.fromFilePath(audioPath);
            
            for (const to of toList) {
                try {
                    const result = await client.sendMessage(to, media, { 
                        sendAudioAsVoice: true,
                        caption 
                    });
                    results.push({ to, success: true, result });
                } catch (error) {
                    results.push({ to, success: false, error: error.message });
                }
            }
            
            return results;
        } catch (error) {
            console.error('Error sending bulk voice messages:', error);
            throw error;
        }
    }

    async downloadVoiceMessage(message) {
        try {
            if (!message.hasMedia) {
                throw new Error('Message does not contain media');
            }

            const media = await message.downloadMedia();
            const buffer = Buffer.from(media.data, 'base64');
            
            const filename = `voice_${Date.now()}.${media.mimetype.split('/')[1]}`;
            const filepath = path.join(__dirname, 'downloads', filename);
            
            if (!fs.existsSync(path.dirname(filepath))) {
                fs.mkdirSync(path.dirname(filepath), { recursive: true });
            }
            
            fs.writeFileSync(filepath, buffer);
            return { filepath, filename, mimetype: media.mimetype };
        } catch (error) {
            console.error('Error downloading voice message:', error);
            throw error;
        }
    }

    async sendConversationFlow(to, messages, timeoutMs = 30000) {
        try {
            const client = await whatsappManager.initialize();
            const conversationResults = [];
            
            for (let i = 0; i < messages.length; i++) {
                const message = messages[i];
                let messageResult;
                
                if (typeof message === 'string') {
                    messageResult = await client.sendMessage(to, message);
                } else if (message.type === 'text') {
                    messageResult = await client.sendMessage(to, message.content);
                } else if (message.type === 'voice') {
                    const media = MessageMedia.fromFilePath(message.content);
                    messageResult = await client.sendMessage(to, media, { 
                        sendAudioAsVoice: true,
                        caption: message.caption || ''
                    });
                } else if (message.type === 'image') {
                    const media = MessageMedia.fromFilePath(message.content);
                    messageResult = await client.sendMessage(to, media, { 
                        caption: message.caption || ''
                    });
                }
                
                conversationResults.push({
                    messageIndex: i,
                    message: message,
                    result: messageResult,
                    timestamp: new Date()
                });
                
                if (i < messages.length - 1) {
                    await this.waitForResponse(client, to, timeoutMs);
                }
            }
            
            return conversationResults;
        } catch (error) {
            console.error('Error in conversation flow:', error);
            throw error;
        }
    }

    async waitForResponse(client, from, timeoutMs) {
        return new Promise((resolve, reject) => {
            const timeout = setTimeout(() => {
                reject(new Error('Timeout waiting for response'));
            }, timeoutMs);
            
            const messageHandler = (message) => {
                if (message.from === from) {
                    clearTimeout(timeout);
                    client.removeListener('message_create', messageHandler);
                    resolve(message);
                }
            };
            
            client.on('message_create', messageHandler);
        });
    }
}

const messageHandler = new MessageHandler();
module.exports = messageHandler;
