const { Client, MessageMedia, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const fs = require('fs');
const path = require('path');
const mongoose = require('mongoose');

// Import fetch for Node.js compatibility
const fetch = (...args) => import('node-fetch').then(({default: fetch}) => fetch(...args));

class WhatsAppManager {
    constructor() {
        this.client = null;
        this.isInitialized = false;
        this.connectionPromise = null;
        
        // Configuration for allowed chat - only this chat can receive messages
        this.allowedChatId = null; // Will be set via setAllowedChat method
        
        // Define the UserReply model schema once
        this.userReplySchema = new mongoose.Schema({
            newsIndex: Number,
            newsUrl: String,
            newsContent: String,
            stats: mongoose.Schema.Types.Mixed, 
            phoneNumber: String,
            groupIndex: Number,
            groupSize: Number,
            createdAt: { type: Date, default: Date.now }
        });
          
        
        // Create the model once
        this.UserReply = mongoose.model('labeleddata1', this.userReplySchema);
    }

    // Set the allowed chat ID - only this chat can receive messages
    setAllowedChat(chatId) {
        this.allowedChatId = chatId;
        console.log(`✅ Allowed chat set to: ${chatId}`);
    }

    // Validate if a chat ID is allowed
    isChatAllowed(chatId) {
        if (!this.allowedChatId) {
            console.warn('⚠️ No allowed chat set. All chats are currently allowed.');
            return true; // If no restriction set, allow all
        }
        
        const isAllowed = chatId === this.allowedChatId;
        if (!isAllowed) {
            console.error(`❌ Chat ${chatId} is not allowed. Only ${this.allowedChatId} is allowed.`);
        }
        return isAllowed;
    }

    // Get the currently allowed chat ID
    getAllowedChat() {
        return this.allowedChatId;
    }

    // Start chatting with the allowed chat
    async startChatting(phoneNumber = null) {
        try {
            console.log('🚀 Starting WhatsApp chat...');
            
            // Wait for connection
            await this.waitForConnection();
            console.log('✅ WhatsApp connection established');
            
            // Ensure client is ready
            await this.ensureClientReady();
            console.log('✅ WhatsApp client is ready');
            
            let chatInfo;
            
            if (phoneNumber) {
                // Find chat by provided phone number
                console.log(`🔍 Looking for chat with phone number: ${phoneNumber}`);
                chatInfo = await this.findChatByPhone(phoneNumber);
                
                if (!chatInfo.found) {
                    console.error('❌ Chat not found. Available chats:');
                    console.log(chatInfo.availableChats);
                    return { success: false, error: 'Chat not found' };
                }
                
                // Set this as the allowed chat
                this.setAllowedChat(chatInfo.chatId);
                console.log(`🔒 Chat restriction enabled - only ${chatInfo.name} can receive messages`);
            } else {
                // Use existing allowed chat
                if (!this.allowedChatId) {
                    console.error('❌ No allowed chat set. Please provide a phone number or set an allowed chat first.');
                    return { success: false, error: 'No allowed chat set' };
                }
                
                chatInfo = {
                    chatId: this.allowedChatId,
                    name: 'Allowed Chat',
                    found: true
                };
                console.log(`✅ Using existing allowed chat: ${this.allowedChatId}`);
            }
            
            console.log(`📱 Ready to chat with: ${chatInfo.name} (${chatInfo.chatId})`);
            console.log('💬 You can now send messages using the WhatsAppManager methods');
            
            return {
                success: true,
                chatInfo: chatInfo,
                message: 'Chat started successfully!'
            };
            
        } catch (error) {
            console.error('❌ Error starting chat:', error);
            return { success: false, error: error.message };
        }
    }

    // Send a simple test message to verify chat is working
    async sendTestMessage(message = "Hello! This is a test message from WhatsApp Bot.") {
        try {
            if (!this.allowedChatId) {
                throw new Error('No allowed chat set. Please start chatting first.');
            }
            
            console.log(`📤 Sending test message to ${this.allowedChatId}...`);
            const result = await this.sendText(this.allowedChatId, message);
            console.log('✅ Test message sent successfully!');
            return { success: true, result: result };
            
        } catch (error) {
            console.error('❌ Error sending test message:', error);
            return { success: false, error: error.message };
        }
    }

    // Send a direct message to a specific chat ID
    async sendDirectMessage(chatId, message) {
        try {
            console.log(`📤 Sending direct message to ${chatId}...`);
            const result = await this.sendText(chatId, message);
            console.log('✅ Direct message sent successfully!');
            return { success: true, result: result };
            
        } catch (error) {
            console.error('❌ Error sending direct message:', error);
            return { success: false, error: error.message };
        }
    }

    // Check if session already exists
    hasExistingSession() {
        const sessionPath = path.join(process.cwd(), '.wwebjs_auth', 'session-whatsapp-annotation-session');
        return fs.existsSync(sessionPath);
    }

    async initialize() {
        if (this.isInitialized) {
            console.log('WhatsApp client already initialized');
            console.log("this.client", this.client);
            return this.client;
        }

        // Check if we have an existing session
        if (this.hasExistingSession()) {
            console.log('✅ Found existing WhatsApp session - no QR code needed!');
        } else {
            console.log('⚠️ No existing session found - QR code will be required');
        }

        console.log('Initializing WhatsApp client...');
        this.client = new Client({
            authStrategy: new LocalAuth({
                clientId: 'whatsapp-annotation-session'
            }),
            puppeteer: {
                headless: true,
                args: [
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-web-security',
                    '--disable-features=VizDisplayCompositor',
                    '--disable-background-timer-throttling',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-renderer-backgrounding',
                    '--disable-extensions',
                    '--disable-plugins',
                    '--disable-default-apps',
                    '--disable-sync',
                    '--disable-translate',
                    '--hide-scrollbars',
                    '--mute-audio',
                    '--no-first-run',
                    '--disable-ipc-flooding-protection'
                ],
                timeout: 0,
                protocolTimeout: 0
            },
            restartOnAuthFail: true,
            webVersionCache: {
                type: 'remote',
                remotePath: 'https://raw.githubusercontent.com/wppconnect-team/wa-version/main/html/2.2412.54.html',
            }
        });

        console.log("this.client", this.client);
        
        return new Promise((resolve, reject) => {
            let resolved = false;
            let isAuthenticated = false;
            let qrShown = false;
            
            const safeResolve = (client) => {
                if (!resolved) {
                    resolved = true;
                    this.isInitialized = true;
                    clearTimeout(timeout);
                    resolve(client);
                }
            };
            
            const safeReject = (error) => {
                if (!resolved) {
                    resolved = true;
                    clearTimeout(timeout);
                    reject(error);
                }
            };
            
            this.client.on('ready', () => {
                console.log('WhatsApp client is ready!');
                safeResolve(this.client);
            });

            this.client.on('qr', qr => {
                console.log('Scan this QR code to connect:');
                qrcode.generate(qr, {small: true});
                qrShown = true;
            });

            this.client.on('authenticated', () => {
                console.log('WhatsApp authenticated successfully!');
                isAuthenticated = true;
                console.log('Waiting for WhatsApp Web to fully load...');
                
                // Check if client is ready after authentication
                setTimeout(() => {
                    this.client.getState().then(state => {
                        console.log(`Client state after authentication: ${state}`);
                        if (state === 'CONNECTED') {
                            console.log('Client is ready after authentication!');
                            safeResolve(this.client);
                        }
                    }).catch(err => {
                        console.log('Error checking client state:', err.message);
                    });
                }, 3000);
            });

            this.client.on('auth_failure', (msg) => {
                console.error('WhatsApp authentication failed:', msg);
                safeReject(new Error('Authentication failed: ' + msg));
            });

            this.client.on('disconnected', (reason) => {
                console.log('WhatsApp disconnected:', reason);
                this.isInitialized = false;
            });

            this.client.on('message_create', message => {
                console.log('Received message:', message.body);
                if (message.body === '!ping') {
                    this.client.sendMessage(message.from, 'pong');
                }
            });

            // Add timeout to prevent hanging
            const timeout = setTimeout(() => {
                if (!resolved) {
                    if (qrShown && !isAuthenticated) {
                        console.error('WhatsApp QR code was shown but authentication timed out after 300 seconds');
                        safeReject(new Error('WhatsApp authentication timeout after 300 seconds'));
                    } else if (isAuthenticated) {
                        console.log('Authentication completed but ready event not fired, proceeding anyway...');
                        safeResolve(this.client);
                    } else {
                        console.error('WhatsApp initialization timeout after 300 seconds');
                        safeReject(new Error('WhatsApp initialization timeout after 300 seconds'));
                    }
                }
            }, 300000);

            // Try to initialize
            this.client.initialize().then(() => {
                console.log('Client initialization completed');
            }).catch(error => {
                console.error('Error initializing WhatsApp client:', error);
                safeReject(error);
            });
        });
    }

    getClient() {
        if (!this.isInitialized) {
            throw new Error('WhatsApp client not initialized. Call initialize() first.');
        }
        return this.client;
    }

    async waitForConnection() {
        if (this.isInitialized) {
            console.log('WhatsApp already connected');
            return this.client;
        }
        
        console.log('Waiting for WhatsApp connection...');
        try {
            const client = await this.initialize();
            console.log('WhatsApp connection established successfully');
            return client;
        } catch (error) {
            console.error('Failed to establish WhatsApp connection:', error.message);
            throw error;
        }
    }

    isConnected() {
        return this.isInitialized && this.client !== null;
    }

    async ensureClientReady() {
        if (!this.isInitialized) {
            await this.initialize();
        }
        
        // Wait for WhatsApp Web to be fully loaded
        console.log('Waiting for WhatsApp Web to be fully ready...');
        await new Promise(resolve => setTimeout(resolve, 10000)); // Wait 10 seconds
        
        // Check client state
        try {
            const client = this.client;
            const state = await client.getState();
            console.log(`WhatsApp client state: ${state}`);
            
            if (state === 'CONNECTED') {
                console.log('WhatsApp Web appears to be ready!');
                return this.client;
            } else {
                console.log(`Client state is ${state}, but proceeding anyway...`);
                return this.client;
            }
        } catch (error) {
            console.log(`Error checking client state: ${error.message}, but proceeding anyway...`);
            return this.client;
        }
    }

    async checkClientHealth() {
        try {
            const client = this.client;
            const state = await client.getState();
            return state === 'CONNECTED';
        } catch (error) {
            console.log(`Client health check failed: ${error.message}`);
            return false;
        }
    }

    async sendMessageDirectly(to, message) {
        try {
            const client = this.client;
            const chatId = to.includes('@') ? to : `${to}@c.us`;

            
            // Send message using direct WhatsApp Web API
            const result = await client.pupPage.evaluate(async (chatId, messageText) => {
                try {
                    // Find or create chat
                    let chat = await window.Store.Chat.find(chatId);
                    if (!chat) {
                        // Try to create a new chat
                        chat = await window.Store.Chat.find(chatId);
                        if (!chat) {
                            throw new Error(`Chat ${chatId} not found and cannot be created`);
                        }
                    }
                    
                    // Send the message
                    const messageObj = await window.Store.SendTextMsg(chat, messageText);
                    return { 
                        success: true, 
                        messageId: messageObj.id,
                        chatId: chatId
                    };
                } catch (error) {
                    console.error('Direct send error:', error);
                    throw new Error(`Direct send failed: ${error.message}`);
                }
            }, chatId, message);
            
            return result;
        } catch (error) {
            console.log(`Direct send failed: ${error.message}`);
            throw error;
        }
    }

    async sendMessageWithFallback(to, message) {
        
            
            // Fallback to regular method
            try {
                const client = this.client;
                return await client.sendMessage(to, message);
            } catch (regularError) {
                console.log(`Regular method also failed: ${regularError.message}`);
                throw new Error(`Both methods failed. Direct: ${directError.message}, Regular: ${regularError.message}`);
            }
        }
    

    async sendText(to, text) {
        try {
            // Validate if chat is allowed
            if (!this.isChatAllowed(to)) {
                throw new Error(`Sending to ${to} is not allowed. Only ${this.allowedChatId} is allowed.`);
            }

            const client = await this.initialize();
            return await client.sendMessage(to, text);
        } catch (error) {
            console.error('Error sending text message:', error);
            throw error;
        }
    }

    async sendImage(to, imagePath, caption = '') {
        try {
            // Validate if chat is allowed
            if (!this.isChatAllowed(to)) {
                throw new Error(`Sending to ${to} is not allowed. Only ${this.allowedChatId} is allowed.`);
            }

            const client = await this.initialize();
            
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
            const client = await this.initialize();
            
            const media = new MessageMedia('image/jpeg', imageBuffer.toString('base64'), filename);
            return await client.sendMessage(to, media, { caption });
        } catch (error) {
            console.error('Error sending image from buffer:', error);
            throw error;
        }
    }

    async sendImageFromUrl(to, imageUrl, caption = '') {
        try {
            const client = await this.initialize();
            
            const response = await fetch(imageUrl);
            const imageBuffer = await response.arrayBuffer();
            const media = new MessageMedia('image/jpeg', Buffer.from(imageBuffer).toString('base64'));
            
            return await client.sendMessage(to, media, { caption });
        } catch (error) {
            console.error('Error sending image from URL:', error);
            throw error;
        }
    }

    async sendVoiceMessage(to, audioPath, caption = '') {
        try {
            const client = await this.initialize();
            
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
            const client = await this.initialize();
            
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
            const client = await this.initialize();
            
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
            const client = await this.initialize();
            const results = [];
            
            for (const to of toList) {
                try {
                    // Validate if chat is allowed
                    if (!this.isChatAllowed(to)) {
                        results.push({ 
                            to, 
                            success: false, 
                            error: `Sending to ${to} is not allowed. Only ${this.allowedChatId} is allowed.` 
                        });
                        continue;
                    }

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

    async sendBulkImage(toList, imagePath, caption = '') {
        try {
            const client = await this.initialize();
            const results = [];
            
            if (!fs.existsSync(imagePath)) {
                throw new Error('Image file not found');
            }

            const media = MessageMedia.fromFilePath(imagePath);
            
            for (const to of toList) {
                try {
                    const result = await client.sendMessage(to, media, { caption });
                    results.push({ to, success: true, result });
                } catch (error) {
                    results.push({ to, success: false, error: error.message });
                }
            }
            
            return results;
        } catch (error) {
            console.error('Error sending bulk image messages:', error);
            throw error;
        }
    }

    async sendBulkVoice(toList, audioPath, caption = '') {
        try {
            const client = await this.initialize();
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

    async sendConversationFlow(to, messages, timeoutMs = 40000) {
        try {
            const client = await this.initialize();
            const conversationResults = [];
            
            // Check if the chat exists and is accessible
            try {
                const chat = await client.getChatById(to);
                if (!chat) {
                    throw new Error(`Chat not found for ${to}`);
                }
                console.log(`Using existing chat: ${chat.name || chat.id._serialized}`);
                
                // Ensure the chat is loaded and ready
                await chat.sendSeen();
                console.log('Chat is ready for messaging');
                
            } catch (chatError) {
                console.error(`Error accessing chat ${to}:`, chatError.message);
                throw new Error(`Cannot access chat for ${to}. Make sure this is an existing conversation.`);
            }
            
            for (let i = 0; i < messages.length; i++) {
                const message = messages[i];
                let messageResult;
                
                try {
                    // Add delay between messages to avoid rate limiting
                    if (i > 0) {
                        await new Promise(resolve => setTimeout(resolve, 1000));
                    }
                    
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
                    
                    console.log(`Message ${i + 1} sent successfully`);
                    
                    conversationResults.push({
                        messageIndex: i,
                        message: message,
                        result: messageResult,
                        timestamp: new Date(),
                        success: true
                    });
                    
                    if (i < messages.length - 1) {
                        console.log('Waiting for response...');
                        const userResponse = await this.waitForResponse(client, to, timeoutMs);
                        console.log(`User responded: "${userResponse.body}"`);
                        
                        // Send follow-up message after receiving response
                        const followUpMessage = this.generateFollowUpMessage(userResponse.body, i + 1);
                        if (followUpMessage) {
                            console.log('Sending follow-up message...');
                            await client.sendMessage(to, followUpMessage);
                            console.log('Follow-up message sent!');
                        }
                    }
                    
                } catch (messageError) {
                    console.error(`Error sending message ${i + 1}:`, messageError);
                    conversationResults.push({
                        messageIndex: i,
                        message: message,
                        error: messageError.message,
                        timestamp: new Date(),
                        success: false
                    });
                    
                    // Continue with next message instead of stopping
                    continue;
                }
            }
            
            return conversationResults;
        } catch (error) {
            console.error('Error in conversation flow:', error);
            throw error;
        }
    }

    generateFollowUpMessage(userResponse, messageIndex) {
        // Customize follow-up messages based on user response and message index
        const response = userResponse.toLowerCase();
        
        if (messageIndex === 1) { // After first message
            if (response.includes('good') || response.includes('great') || response.includes('fine')) {
                return "That's wonderful! I'm glad to hear you're doing well.";
            } else if (response.includes('bad') || response.includes('not good') || response.includes('terrible')) {
                return "I'm sorry to hear that. Is there anything I can help you with?";
            } else {
                return "Thank you for your response! I appreciate you taking the time to reply.";
            }
        } else if (messageIndex === 2) { // After second message
            if (response.includes('yes') || response.includes('sure') || response.includes('okay')) {
                return "Great! I'm here to help. What would you like to know more about?";
            } else if (response.includes('no') || response.includes('not really')) {
                return "No problem at all! Feel free to reach out if you need anything later.";
            } else {
                return "Thanks for sharing your thoughts with me!";
            }
        }
        
        return null; // No follow-up for other messages
    }

    async sendSmartConversation(to, initialMessages, followUpRules = null, timeoutMs = 30000) {
        try {
            const client = await this.initialize();
            const conversationResults = [];
            
            // Check if the chat exists and is accessible
            try {
                const chat = await client.getChatById(to);
                if (!chat) {
                    throw new Error(`Chat not found for ${to}`);
                }
                console.log(`Using existing chat: ${chat.name || chat.id._serialized}`);
                await chat.sendSeen();
                console.log('Chat is ready for messaging');
            } catch (chatError) {
                console.error(`Error accessing chat ${to}:`, chatError.message);
                throw new Error(`Cannot access chat for ${to}. Make sure this is an existing conversation.`);
            }
            
            // Send first message and wait for user response
            console.log('Sending first message and waiting for user to respond...');
            const firstMessage = initialMessages[0];
            let messageResult;
            
            if (typeof firstMessage === 'string') {
                messageResult = await client.sendMessage(to, firstMessage);
            } else if (firstMessage.type === 'text') {
                messageResult = await client.sendMessage(to, firstMessage.content);
            } else if (firstMessage.type === 'voice') {
                const media = MessageMedia.fromFilePath(firstMessage.content);
                messageResult = await client.sendMessage(to, media, { 
                    sendAudioAsVoice: true,
                    caption: firstMessage.caption || ''
                });
            } else if (firstMessage.type === 'image') {
                const media = MessageMedia.fromFilePath(firstMessage.content);
                messageResult = await client.sendMessage(to, media, { 
                    caption: firstMessage.caption || ''
                });
            }
            
            console.log('First message sent successfully');
            conversationResults.push({
                messageIndex: 0,
                message: firstMessage,
                result: messageResult,
                timestamp: new Date(),
                success: true,
                type: 'initial'
            });
            
            // Wait for user to send first response
            console.log('Waiting for user to send first message...');
            const firstUserResponse = await this.waitForResponse(client, to, timeoutMs);
            console.log(`User sent first message: "${firstUserResponse.body}"`);
            
            // Send follow-up based on first response
            const firstFollowUp = this.generateSmartFollowUp(firstUserResponse.body, followUpRules);
            if (firstFollowUp) {
                console.log('Sending follow-up to first user message...');
                const followUpResult = await client.sendMessage(to, firstFollowUp);
                console.log('First follow-up sent!');
                
                conversationResults.push({
                    messageIndex: 0,
                    message: firstFollowUp,
                    result: followUpResult,
                    timestamp: new Date(),
                    success: true,
                    type: 'follow-up',
                    triggeredBy: firstUserResponse.body
                });
            }
            
            // Now wait for user to send another message before sending next bot message
            console.log('Waiting for user to send another message...');
            const secondUserResponse = await this.waitForResponse(client, to, timeoutMs);
            console.log(`User sent second message: "${secondUserResponse.body}"`);
            
            // Now send the second bot message
            if (initialMessages.length > 1) {
                console.log('Sending second bot message...');
                const secondMessage = initialMessages[1];
                
                if (typeof secondMessage === 'string') {
                    messageResult = await client.sendMessage(to, secondMessage);
                } else if (secondMessage.type === 'text') {
                    messageResult = await client.sendMessage(to, secondMessage.content);
                } else if (secondMessage.type === 'voice') {
                    const media = MessageMedia.fromFilePath(secondMessage.content);
                    messageResult = await client.sendMessage(to, media, { 
                        sendAudioAsVoice: true,
                        caption: secondMessage.caption || ''
                    });
                } else if (secondMessage.type === 'image') {
                    const media = MessageMedia.fromFilePath(secondMessage.content);
                    messageResult = await client.sendMessage(to, media, { 
                        caption: secondMessage.caption || ''
                    });
                }
                
                console.log('Second message sent successfully');
                conversationResults.push({
                    messageIndex: 1,
                    message: secondMessage,
                    result: messageResult,
                    timestamp: new Date(),
                    success: true,
                    type: 'initial'
                });
                
                // Wait for user response to second message
                console.log('Waiting for user response to second message...');
                const thirdUserResponse = await this.waitForResponse(client, to, timeoutMs);
                console.log(`User responded to second message: "${thirdUserResponse.body}"`);
                
                // Send follow-up to second response
                const secondFollowUp = this.generateSmartFollowUp(thirdUserResponse.body, followUpRules);
                if (secondFollowUp) {
                    console.log('Sending follow-up to second user message...');
                    const followUpResult = await client.sendMessage(to, secondFollowUp);
                    console.log('Second follow-up sent!');
                    
                    conversationResults.push({
                        messageIndex: 1,
                        message: secondFollowUp,
                        result: followUpResult,
                        timestamp: new Date(),
                        success: true,
                        type: 'follow-up',
                        triggeredBy: thirdUserResponse.body
                    });
                }
                
                // Wait for another user message before sending third bot message
                if (initialMessages.length > 2) {
                    console.log('Waiting for user to send another message...');
                    const fourthUserResponse = await this.waitForResponse(client, to, timeoutMs);
                    console.log(`User sent another message: "${fourthUserResponse.body}"`);
                    
                    // Send third bot message
                    console.log('Sending third bot message...');
                    const thirdMessage = initialMessages[2];
                    
                    if (typeof thirdMessage === 'string') {
                        messageResult = await client.sendMessage(to, thirdMessage);
                    } else if (thirdMessage.type === 'text') {
                        messageResult = await client.sendMessage(to, thirdMessage.content);
                    } else if (thirdMessage.type === 'voice') {
                        const media = MessageMedia.fromFilePath(thirdMessage.content);
                        messageResult = await client.sendMessage(to, media, { 
                            sendAudioAsVoice: true,
                            caption: thirdMessage.caption || ''
                        });
                    } else if (thirdMessage.type === 'image') {
                        const media = MessageMedia.fromFilePath(thirdMessage.content);
                        messageResult = await client.sendMessage(to, media, { 
                            caption: thirdMessage.caption || ''
                        });
                    }
                    
                    console.log('Third message sent successfully');
                    conversationResults.push({
                        messageIndex: 2,
                        message: thirdMessage,
                        result: messageResult,
                        timestamp: new Date(),
                        success: true,
                        type: 'initial'
                    });
                }
            }
            
            return conversationResults;
        } catch (error) {
            console.error('Error in smart conversation:', error);
            throw error;
        }
    }

    generateSmartFollowUp(userResponse, followUpRules) {
        const response = userResponse.toLowerCase();
        
        // Default follow-up rules if none provided
        const defaultRules = {
            'help': 'I can help you with various tasks. What specifically do you need assistance with?',
            'question': 'That\'s a great question! Let me think about the best way to answer that.',
            'thanks': 'You\'re very welcome! I\'m here to help anytime.',
            'bye': 'Goodbye! Have a wonderful day ahead!',
            'name': 'My name is WhatsApp Bot. How can I assist you today?',
            'weather': 'I can\'t check the weather, but I can help you with other tasks!',
            'time': 'I don\'t have access to real-time information, but I\'m here to help with other things!'
        };
        
        // Use custom rules if provided, otherwise use defaults
        const rules = followUpRules || defaultRules;
        
        // Check for keywords in the response
        for (const [keyword, followUp] of Object.entries(rules)) {
            if (response.includes(keyword)) {
                return followUp;
            }
        }
        
        // If no specific keyword match, send a general response
        if (response.length < 10) {
            return 'Could you please elaborate a bit more? I\'d love to help you better.';
        } else if (response.includes('?')) {
            return 'That\'s an interesting question! Let me think about how I can best assist you.';
        } else {
            return 'Thank you for your message! I\'m here to help with whatever you need.';
        }
    }

    async waitForResponse(client, from, timeoutMs) {
        return new Promise((resolve, reject) => {
            const timeout = setTimeout(() => {
                reject(new Error(`Timeout waiting for response from ${from} after ${timeoutMs}ms`));
            }, timeoutMs);
            
            const messageHandler = (message) => {
                // Only handle messages from the specific user we're waiting for
                if (message.from === from && message.body && message.body.trim().length > 0) {
                    console.log(`Received reply from user: "${message.body}"`);
                    clearTimeout(timeout);
                    client.removeListener('message_create', messageHandler);
                    resolve(message);
                }
            };
            
            // Listen for new messages
            client.on('message_create', messageHandler);
            
            console.log(`Waiting for reply from ${from}... (timeout: ${timeoutMs}ms)`);
        });
    }

    async downloadMedia(message, downloadPath = null) {
        try {
            if (!message.hasMedia) {
                throw new Error('Message does not contain media');
            }

            const media = await message.downloadMedia();
            const buffer = Buffer.from(media.data, 'base64');
            
            if (!downloadPath) {
                const timestamp = Date.now();
                const extension = media.mimetype.split('/')[1];
                const filename = `media_${timestamp}.${extension}`;
                downloadPath = path.join(__dirname, 'downloads', filename);
            }
            
            if (!fs.existsSync(path.dirname(downloadPath))) {
                fs.mkdirSync(path.dirname(downloadPath), { recursive: true });
            }
            
            fs.writeFileSync(downloadPath, buffer);
            return { 
                filepath: downloadPath, 
                filename: path.basename(downloadPath), 
                mimetype: media.mimetype 
            };
        } catch (error) {
            console.error('Error downloading media:', error);
            throw error;
        }
    }

    async getChats() {
        try {
            const client = await this.initialize();
            console.log("client", client);
            chats =  await client.getChats();
            return chats;
        } catch (error) {
            console.error('Error getting chats:', error);
            throw error;
        }
    }

    async getContacts() {
        try {
            const client = await this.initialize();
            return await client.getContacts();
        } catch (error) {
            console.error('Error getting contacts:', error);
            throw error;
        }
    }

    async getProfilePicFromServer(contactId) {
        try {
            const client = await this.initialize();
            return await client.getProfilePicFromServer(contactId);
        } catch (error) {
            console.error('Error getting profile picture:', error);
            throw error;
        }
    }

    async isRegisteredUser(contactId) {
        try {
            const client = await this.initialize();
            return await client.isRegisteredUser(contactId);
        } catch (error) {
            console.error('Error checking if user is registered:', error);
            throw error;
        }
    }

    async checkChatExists(chatId) {
        try {
            const client = await this.initialize();
            
            // First try the exact chatId
            try {
                const chat = await client.getChatById(chatId);
                if (chat) {
                    return {
                        exists: true,
                        chat: chat,
                        name: chat.name || chat.id._serialized
                    };
                }
            } catch (exactError) {
                console.log(`Exact match failed for ${chatId}:`, exactError.message);
            }
            
            // If exact match fails, try to find by phone number
            const allChats = await client.getChats();
            const phoneNumber = chatId.replace('@c.us', '');
            
            for (const chat of allChats) {
                const chatPhone = chat.id._serialized.replace('@c.us', '');
                if (chatPhone === phoneNumber) {
                    console.log(`Found chat by phone number: ${chat.id._serialized}`);
                    return {
                        exists: true,
                        chat: chat,
                        name: chat.name || chat.id._serialized
                    };
                }
            }
            
            return {
                exists: true,
                error: `Chat not found for ${chatId}`
            };
        } catch (error) {
            return {
                exists: false,
                error: error.message
            };
        }
    }

    async listAvailableChats() {
        try {
            const client = await this.initialize();
            const chats = await client.getChats();
            return chats.map(chat => ({
                id: chat.id._serialized,
                name: chat.name || 'Unknown',
                isGroup: chat.isGroup,
                unreadCount: chat.unreadCount
            }));
        } catch (error) {
            console.error('Error listing chats:', error);
            throw error;
        }
    }

    async testConnection(chatId) {
        try {
            const client = await this.initialize();
            console.log('Testing connection by sending a simple message...');
            
            // const result = await client.sendMessage(chatId, 'Test message - connection working!');
            // console.log('Test message sent successfully!');
            
            return { success: true };
        } catch (error) {
            console.error('Test message failed:', error);
            return { success: false, error: error.message };
        }
    }

    async findChatByPhone(phoneNumber) {
        try {
            const client = await this.ensureClientReady();
            
            // Remove any formatting from phone number
            const cleanPhone = phoneNumber.replace(/\D/g, '');
            const chatId = `${cleanPhone}@c.us`;
            
            // Try to get chats, but if it fails, assume the chat exists and try to use it directly
            try {
                const allChats = await client.getChats();
                console.log(`Successfully retrieved ${allChats.length} chats`);
            
            for (const chat of allChats) {
                const chatPhone = chat.id._serialized.replace('@c.us', '');
                if (chatPhone === cleanPhone) {
                    return {
                        found: true,
                        chatId: chat.id._serialized,
                        name: chat.name || chat.id._serialized,
                        chat: chat
                    };
                }
            }
            
            return {
                found: false,
                availableChats: allChats.map(chat => ({
                    id: chat.id._serialized,
                    name: chat.name || 'Unknown',
                    phone: chat.id._serialized.replace('@c.us', '')
                }))
            };
            } catch (chatsError) {
                console.log(`getChats() failed (${chatsError.message}), assuming chat exists and proceeding...`);
                
                // If getChats fails, assume the chat exists and return the expected format
                return {
                    found: true,
                    chatId: chatId,
                    name: `Chat ${cleanPhone}`,
                    chat: null // We can't get the actual chat object, but we can try to use the ID
                };
            }
        } catch (error) {
            console.error('Error finding chat by phone:', error);
            return { found: false, error: error.message };
        }
    }

    async sendWaitForUserConversation(to, messages, timeoutMs = 30000) {
        try {
            const client = await this.initialize();
            const conversationResults = [];
            
            try {
                const chat = await client.getChatById(to);
                if (!chat) {
                    throw new Error(`Chat not found for ${to}`);
                }
                console.log(`Using existing chat: ${chat.name || chat.id._serialized}`);
                await chat.sendSeen();
                console.log('Chat is ready for messaging');
            } catch (chatError) {
                console.error(`Error accessing chat ${to}:`, chatError.message);
                throw new Error(`Cannot access chat for ${to}. Make sure this is an existing conversation.`);
            }
            
            console.log(`Starting conversation with ${messages.length} questions...`);
            
            // Loop through all messages
            for (let i = 0; i < messages.length; i++) {
                const message = messages[i];
                
                // Send the current message
                console.log(`\n--- Question ${i + 1}/${messages.length} ---`);
                console.log(`Sending: "${message}"`);
                
                let messageResult = await client.sendMessage(to, message);
                
                console.log(`Question ${i + 1} sent successfully`);
                conversationResults.push({
                    messageIndex: i,
                    message: message,
                    result: messageResult,
                    timestamp: new Date(),
                    success: true
                });
                
                // Wait for user reply (except for the last message)
                if (i < messages.length - 1) {
                    console.log(`Waiting for user reply to question ${i + 1}...`);
                    const userReply = await this.waitForResponse(client, to, timeoutMs);
                    console.log(`User replied: "${userReply.body}"`);
                    
                    // Add user reply to results
                    conversationResults.push({
                        messageIndex: i,
                        userReply: userReply.body,
                        timestamp: new Date(),
                        type: 'user_response'
                    });
                } else {
                    console.log('This was the last question. No need to wait for reply.');
                }
            }
            
            console.log('\n=== CONVERSATION FLOW COMPLETED ===');
            console.log(`Total questions sent: ${conversationResults.filter(r => r.type !== 'user_response').length}`);
            console.log(`Total user replies received: ${conversationResults.filter(r => r.type === 'user_response').length}`);
            console.log('All questions sent and replies received successfully!');
            console.log('=====================================\n');
            
            return conversationResults;
        } catch (error) {
            console.error('Error in wait-for-user conversation:', error);
            throw error;
        }
    }

    async sendNewsAndWaitForReplies(to, jsonFilePath, outputFilePath, timeoutMs = 30000, startFromIndex = 0) {
        try {
            // Validate if chat is allowed
            if (!this.isChatAllowed(to)) {
                throw new Error(`Sending to ${to} is not allowed. Only ${this.allowedChatId} is allowed.`);
            }

            const client = await this.initialize();
            console.log('📁 Using file storage mode');
    
            // Resume info
            if (startFromIndex > 0) console.log(`🔄 Resuming from index ${startFromIndex}`);
    
            // Load JSON data
            const jsonData = JSON.parse(fs.readFileSync(jsonFilePath, 'utf8'));
            const newsItems = [];

            // --- Extract news items ---
            if (Array.isArray(jsonData)) {
                jsonData.forEach((item, index) => {
                    if (item.content?.trim()?.length > 0) {
                        newsItems.push({
                            index,
                            url: item.url || 'No URL available',
                            content: item.content,
                            title: item.title || `News Item ${index + 1}`
                        });
                    }
                });
            } else if (jsonData.url && jsonData.text) {
                const urlData = jsonData.url;
                const textData = jsonData.text;
                const allKeys = new Set([...Object.keys(urlData), ...Object.keys(textData)]);
                const sortedKeys = Array.from(allKeys).sort((a, b) => parseInt(a) - parseInt(b));
                for (const key of sortedKeys) {
                    const url = urlData[key] || 'No URL available';
                    const text = textData[key] || 'No content available';
                    if (text.trim().length > 0) {
                        newsItems.push({
                            index: parseInt(key),
                            url,
                            content: text,
                            title: `News Item ${key}`
                        });
                    }
                }
            }

            console.log(`📰 Found ${newsItems.length} news items to process`);
            console.log(`Starting from index: ${startFromIndex}`);

            const chat = { id: { _serialized: to } };
            const conversationResults = [];
            let processedCount = 0;
            let errorCount = 0;
            
            // Load existing data if file exists
            let existingData = { metadata: null, results: [] };
            if (fs.existsSync(outputFilePath)) {
                try {
                    const fileContent = fs.readFileSync(outputFilePath, 'utf8');
                    existingData = JSON.parse(fileContent);
                    console.log(`📁 Loaded existing data: ${existingData.results.length} items`);
                } catch (err) {
                    console.log('⚠️ Could not read existing file, starting fresh');
                    existingData = { metadata: null, results: [] };
                }
            }

            // --- Grouping config ---
            const itemsPerGroup = 3;
            const totalGroups = Math.ceil((newsItems.length - startFromIndex) / itemsPerGroup);
            
            for (let groupIndex = 0; groupIndex < totalGroups; groupIndex++) {
                const startIndex = startFromIndex + (groupIndex * itemsPerGroup);
                const endIndex = Math.min(startIndex + itemsPerGroup, newsItems.length);
                const groupNewsItems = newsItems.slice(startIndex, endIndex);
                
                try {
                    console.log(`\n--- Processing Group ${groupIndex + 1}/${totalGroups} ---`);
                    console.log(`Items ${startIndex + 1}-${endIndex} of ${newsItems.length}`);
    
                    // --- Compose message ---
                    let message = `📰 *News Group ${groupIndex + 1}* (${groupNewsItems.length} items)\n\n`;
                    groupNewsItems.forEach((newsItem, idx) => {
                        message += `--- *News Item ${startIndex + idx + 1}* ---\n`;
                        message += `*Title:* ${newsItem.title}\n`;
                        message += `*Content:* ${newsItem.content}\n`;
                        message += `🔗 ${newsItem.url}\n\n`;
                    });
                    message += `Please reply only in JSON format.
For each news item provided, add one object to the crimes array.
Each object must include the following details:

Add a key named eng_location containing the province, city, and area in English.

Add another key named location containing the same province, city, and area in Urdu.

If a news item describes more than one event (e.g., multiple crimes or incidents), set is_multi: true, and both eng_location and location should be arrays containing all corresponding locations.

Include accurate latitude and longitude for the location (determine these from a reliable geolocation source).

For suspects, use the keys are role, age, gender.

For victims, use the keys are status, age, gender.

In the role field (for suspects), use one-word values such as "central suspect", "companion", etc.

In the status field (for victims), use one-word values such as "murdered", "wounded", etc.

For age, if the exact age is mentioned in the news, include it. Otherwise, use one of the following age groups: "child", "young", "elderly", or "unknown".

For gender, if the exact gender is specified, include it. Otherwise, use one of the following: "male", "female", or "unknown".\n`;
                    message += `Set newIndex to the displayed item number (e.g., 1, 2, 3).\n`;
                    message += `If an item has multiple victims/suspects, use arrays.\n\n`;
                    message += `To Get the coordinates search on broswer\n`;
                    message += `Example response:\n`;
                    message += `\`\`\`json\n`;
                    message += `{\n`;
                    message += `  "crimes": [\n`;
                    message += `    {\n`;
                    message += `      "url": "(news url)",\n`;
                    message += `      "newIndex": 1,\n`;
                    message += `      "location": { "province": "", "city": "", "area": "", "coordinates": { "latitude": "unknown", "longitude": "unknown" } },\n`;
                    message += `      "victims": [ { "age": "", "gender": "", "status": "" } ],\n`;
                    message += `      "suspects": [ { "age": "", "gender": "", "role": "" } ]\n`;
                    message += `    },\n`;
                    message += `    {\n`;
                    message += `      "newIndex": 2,\n`;
                    message += `      "location": { "province": "", "city": "", "area": "" },\n`;
                    message += `      "victims": [],\n`;
                    message += `      "suspects": []\n`;
                    message += `    },\n`;
                    message += `    { "newIndex": 3, "victims": [], "suspects": [] }\n`;
                    message += `  ]\n`;
                    message += `}\n`;
                    message += `\`\`\`\n\n`;
                    console.log(`Message length: ${message.length} characters`);
                    
                    // --- Send message with retries ---
                    let messageResult;
                    for (let attempt = 1; attempt <= 5; attempt++) {
                        try {
                            console.log(`📤 Sending group (attempt ${attempt})`);
                            messageResult = await this.sendMessageWithFallback(to, message);
                            console.log('✅ Group sent successfully');
                            break;
                        } catch (err) {
                            console.log(`❌ Send failed (attempt ${attempt}): ${err.message}`);
                            if (attempt < 5) {
                                const delay = Math.min(30000, 10000 * attempt);
                                console.log(`⏳ Retrying in ${delay / 1000}s...`);
                                await new Promise(r => setTimeout(r, delay));
                            } else throw err;
                        }
                    }
    
                    processedCount += groupNewsItems.length;
                    
                    // --- Wait for reply ---
                    console.log(`⏳ Waiting for reply to group ${groupIndex + 1}...`);
                    const userReply = await this.waitForResponse(client, to, timeoutMs);
                    console.log(`✅ User replied: "${userReply.body}"`);
                    
                    // --- Parse JSON ---
					let parsedJson = null;
					try {
						const jsonMatch = userReply.body.match(/\{[\s\S]*\}|\[[\s\S]*\]/);
                        if (jsonMatch) parsedJson = JSON.parse(jsonMatch[0]);
                        console.log('✅ Parsed JSON reply');
                    } catch (e) {
                        console.log('⚠️ Failed to parse JSON from reply');
                    }
    
                    // --- Build URL-based crime map ---
                    let urlMappedCrimes = {};
                    if (parsedJson?.crimes && Array.isArray(parsedJson.crimes)) {
                        parsedJson.crimes.forEach(crime => {
                            const crimeUrl = crime.url?.trim();
                            if (crimeUrl) urlMappedCrimes[crimeUrl] = crime;
                        });
                    }
    
                    // --- Helper: index-based fallback matching ---
                    const getCrimesForItem = (allParsed, localItemNumber, originalIndexInSource, localIndexInGroup, absoluteItemNumber) => {
                        if (!allParsed?.crimes) return [];
						const targets = new Set([
							String(localItemNumber), localItemNumber,
							String(localIndexInGroup + 1), localIndexInGroup + 1,
							String(absoluteItemNumber), absoluteItemNumber,
							String(originalIndexInSource), originalIndexInSource
						]);
                        return allParsed.crimes.filter(c => {
							const keys = [c.newIndex, c.index, c.newsIndex];
                            return keys.some(k => targets.has(k) || targets.has(Number(k)) || targets.has(String(k)));
						});
					};
                    
                    // --- Prepare MongoDB documents ---
                    const docsToInsert = [];
    
					for (let itemIndex = 0; itemIndex < groupNewsItems.length; itemIndex++) {
						const newsItem = groupNewsItems[itemIndex];
                        const localItemNumber = itemIndex + 1;
                        const absoluteItemNumber = startIndex + itemIndex + 1;
    
                        // Map by URL or fallback
                        let mappedCrime = urlMappedCrimes[newsItem.url];
                        if (!mappedCrime) {
                            const fallbackCrimes = getCrimesForItem(parsedJson, localItemNumber, newsItem.index, itemIndex, absoluteItemNumber);
                            if (fallbackCrimes.length > 0) mappedCrime = fallbackCrimes[0];
                        }
    
							const docPayload = {
								newsIndex: startIndex + itemIndex,
								newsUrl: newsItem.url,
								newsContent: newsItem.content,
                            ...(mappedCrime ? { stats: mappedCrime } : {}),
								phoneNumber: to,
								groupIndex: groupIndex,
                            groupSize: groupNewsItems.length,
                            createdAt: new Date()
                        };
    
                        docsToInsert.push(docPayload);
                    }
    
                    // --- Store data in file immediately after each group ---
                    if (docsToInsert.length > 0) {
                        // Add new results to existing data
                        existingData.results.push(...docsToInsert);
                        
                        // Update metadata
                        existingData.metadata = {
                            totalNewsItems: newsItems.length,
                            processedCount: processedCount,
                            errorCount: errorCount,
                            totalGroups: totalGroups,
                            itemsPerGroup: itemsPerGroup,
                            phoneNumber: to,
                            startFromIndex: startFromIndex,
                            lastUpdated: new Date().toISOString(),
                            currentGroup: groupIndex + 1
                        };
                        
                        // Save to file immediately
                        try {
                            fs.writeFileSync(outputFilePath, JSON.stringify(existingData, null, 2));
                            console.log(`💾 Saved ${docsToInsert.length} items to file (Group ${groupIndex + 1}/${totalGroups})`);
                            console.log(`📊 Total items in file: ${existingData.results.length}`);
                        } catch (fileErr) {
                            console.error('❌ Error saving to file:', fileErr.message);
                            // Continue processing even if file save fails
                        }
                    }
    
                    // --- Delay before next group ---
                    if (groupIndex < totalGroups - 1) {
                        console.log('⏳ Waiting 5s before next group...');
                        await new Promise(r => setTimeout(r, 5000));
                    }
    
                } catch (err) {
                    console.error(`❌ Error in group ${groupIndex + 1}: ${err.message}`);
                    errorCount += groupNewsItems.length;
                    if (err.message.includes('getChat') || err.message.includes('disconnected')) {
                        console.log('🔄 Connection issue — retrying in 10s...');
                        await new Promise(r => setTimeout(r, 10000));
                    }
                    continue;
                }
            }

            console.log('\n=== ✅ NEWS PROCESSING COMPLETED ===');
            console.log(`Total news items: ${newsItems.length}`);
            console.log(`Processed: ${processedCount}, Errors: ${errorCount}`);
            console.log(`Groups: ${totalGroups} (x${itemsPerGroup} each)`);
            console.log(`📁 Final data saved to: ${outputFilePath}`);
            console.log(`📊 Total records in file: ${existingData.results.length}`);
            
            return conversationResults;
            
        } catch (err) {
            console.error('💥 Fatal error in news processing:', err.message);
            throw err;
        }
    }
    

    async getLastProcessedIndex(outputFilePath, phoneNumber) {
        try {
            console.log('📁 Checking last processed index from file storage');
            
            // Check if the output file exists
            if (!fs.existsSync(outputFilePath)) {
                console.log('No previous processing file found, starting from beginning');
                return 0;
            }
            
            // Read the existing file
            const fileContent = fs.readFileSync(outputFilePath, 'utf8');
            const data = JSON.parse(fileContent);
            
            if (!data.results || !Array.isArray(data.results)) {
                console.log('Invalid file format, starting from beginning');
                return 0;
            }
            
            // Find the highest newsIndex for the given phone number
            let maxIndex = -1;
            for (const result of data.results) {
                if (result.phoneNumber === phoneNumber && result.newsIndex !== undefined) {
                    maxIndex = Math.max(maxIndex, result.newsIndex);
                }
            }
            
            if (maxIndex >= 0) {
                console.log(`Last processed index: ${maxIndex}`);
                console.log(`📊 Found ${data.results.length} total items in file`);
                if (data.metadata) {
                    console.log(`📈 Last updated: ${data.metadata.lastUpdated}`);
                    console.log(`🔄 Current group: ${data.metadata.currentGroup || 'Unknown'}`);
                }
                return maxIndex + 1; // Resume from next item
            } else {
                console.log('No previous processing found for this phone number, starting from beginning');
                return 0;
            }
            
        } catch (error) {
            console.error('Error checking last processed index:', error.message);
            return 0; // Start from beginning if error
        }
    }

    getOrCreateUserReplyModel() {
        try {
            // Try to get existing model first
            if (this.UserReply) {
                return this.UserReply;
            }
            
            // If not exists, try to create it
            this.UserReply = mongoose.model('labeleddata', this.userReplySchema);
            return this.UserReply;
            
        } catch (error) {
            if (error.name === 'OverwriteModelError') {
                // Model already exists, get it
                this.UserReply = mongoose.model('labeleddata');
                return this.UserReply;
            } else {
                // Other error, rethrow
                throw error;
            }
        }
    }
}

const whatsappManager = new WhatsAppManager();
module.exports = whatsappManager;
