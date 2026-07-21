const whatsapp = require('./mannagers/WhatsAppManager.js');

async function main() {
    try {
        console.log('🚀 Starting WhatsApp Chat System...');
        
        // Start chatting with the specified phone number
        const phoneNumber = '18334363285';
        const chatResult = await whatsapp.startChatting(phoneNumber);
        
        if (!chatResult.success) {
            console.error('❌ Failed to start chat:', chatResult.error);
            return;
        }
        
        console.log('✅ Chat started successfully!');
        console.log(`📱 Chatting with: ${chatResult.chatInfo.name} (${chatResult.chatInfo.chatId})`);
        
        // Send a test message to verify everything is working
        console.log('\n📤 Sending test message...');
        const testResult = await whatsapp.sendTestMessage("Hello! WhatsApp Bot is ready to chat. 🚀");
        
        if (testResult.success) {
            console.log('✅ Test message sent successfully!');
        } else {
            console.log('⚠️ Test message failed:', testResult.error);
        }
        
        console.log('\n🎉 WhatsApp Chat System is ready!');
        
        // Send a custom message to the chat
        console.log('\n📤 Sending custom message...');
        const customMessage = "Hello! This is a custom message from WhatsApp Bot. How are you doing today? 😊";
        const customResult = await whatsapp.sendText(chatResult.chatInfo.chatId, customMessage);
        
        if (customResult) {
            console.log('✅ Custom message sent successfully!');
        } else {
            console.log('❌ Custom message failed to send');
        }
        
        // Process news items and store results in file
        const jsonFilePath = 'resources/ahmad.json';

        console.log('\nStarting news processing...');
        
        const outputFilePath = 'resources/output.json';
        
        // Check if we should resume from a previous run
        const lastProcessedIndex = await whatsapp.getLastProcessedIndex(outputFilePath, chatResult.chatInfo.chatId);
        if (lastProcessedIndex > 0) {
            console.log(`🔄 Resuming from index ${lastProcessedIndex} (${lastProcessedIndex} items already processed)`);
        }
        const results = await whatsapp.sendNewsAndWaitForReplies(
            chatResult.chatInfo.chatId,
            jsonFilePath,
            outputFilePath,
            40000, // 40 second timeout for each reply
            lastProcessedIndex // Start from this index
        );
        
        console.log('News processing completed successfully!');
        console.log(`Processed ${results.length} total items`);
        
    } catch (error) {
        console.error('Error in main function:', error);
    }
}

main().catch(console.error);