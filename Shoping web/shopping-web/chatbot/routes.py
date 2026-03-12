from flask import Blueprint, render_template, request, jsonify
from .bot import get_bot_response

chatbot_bp = Blueprint('chatbot', __name__)

@chatbot_bp.route('/chat', methods=['GET'])
def chat():
    return render_template('chat.html')

@chatbot_bp.route('/chat/message', methods=['POST'])
def chat_message():
    user_message = request.json.get('message')
    bot_response = get_bot_response(user_message)
    return jsonify({'response': bot_response})