# Shopping Web Application

This project is a Flask-based web application for an online shopping platform that includes a chatbot feature for user interaction.

## Features

- User registration and login
- Product management (view, add, edit, delete)
- Shopping cart functionality
- Admin dashboard for managing users and products
- Chatbot for customer support and interaction

## Project Structure

```
shopping-web
├── app.py                     # Main application file
├── chatbot                     # Chatbot module
│   ├── __init__.py            # Initializes the chatbot module
│   ├── routes.py              # Defines chatbot-related routes
│   └── bot.py                 # Contains chatbot logic
├── templates                   # HTML templates
│   ├── index.html             # Homepage template
│   ├── product.html           # Product detail template
│   ├── cart.html              # Shopping cart template
│   ├── login.html             # User login template
│   ├── register.html          # User registration template
│   ├── profile.html           # User profile template
│   ├── admin_dashboard.html    # Admin dashboard template
│   ├── admin_login.html       # Admin login template
│   └── chat.html              # Chatbot interface template
├── static                      # Static files (CSS, JS, images)
│   ├── css
│   │   └── styles.css         # CSS styles for the application
│   ├── js
│   │   ├── main.js            # Main JavaScript code
│   │   └── chat.js            # JavaScript for chatbot interactions
│   └── uploads                # Directory for uploaded files
├── tests                       # Test files
│   └── test_chatbot.py        # Unit tests for chatbot functionality
├── requirements.txt            # Project dependencies
├── .env.example                # Example environment variables
└── README.md                   # Project documentation
```

## Installation

1. Clone the repository:
   ```
   git clone <repository-url>
   cd shopping-web
   ```

2. Create a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. Install the required packages:
   ```
   pip install -r requirements.txt
   ```

4. Set up environment variables by copying `.env.example` to `.env` and modifying as needed.

5. Run the application:
   ```
   python app.py
   ```

## Usage

- Visit `http://localhost:5000` to access the application.
- Use the chatbot feature on the chat page to interact with the bot for assistance.

## Contributing

Contributions are welcome! Please submit a pull request or open an issue for any suggestions or improvements.