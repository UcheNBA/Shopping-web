from flask import jsonify

class Chatbot:
    def __init__(self):
        self.responses = {
            "hi": "Hello! How can I assist you today?",
            "how are you?": "I'm just a bot, but thanks for asking!",
            "what is your name?": "I'm your friendly shopping assistant!",
            "help": "You can ask me about products, your cart, or anything else!",
            "bye": "Goodbye! Have a great day!"
        }

    def get_response(self, user_input):
        user_input = user_input.lower()
        return self.responses.get(user_input, "I'm sorry, I didn't understand that.")

chatbot = Chatbot()

def process_message(message):
    return chatbot.get_response(message)