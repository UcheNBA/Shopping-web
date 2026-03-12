from flask import Flask, session
import unittest
from chatbot.bot import ChatBot

class TestChatBot(unittest.TestCase):

    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = 'test_secret'
        self.chatbot = ChatBot()

    def test_greeting(self):
        response = self.chatbot.get_response("Hello")
        self.assertIn("Hello", response)

    def test_farewell(self):
        response = self.chatbot.get_response("Goodbye")
        self.assertIn("Goodbye", response)

    def test_unknown_input(self):
        response = self.chatbot.get_response("What is this?")
        self.assertIn("I'm not sure how to respond to that.", response)

    def test_context_management(self):
        self.chatbot.set_context("user", "shopping")
        response = self.chatbot.get_response("I want to buy something")
        self.assertIn("What would you like to buy?", response)

if __name__ == '__main__':
    unittest.main()