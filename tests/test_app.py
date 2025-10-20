import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import unittest
from unittest.mock import patch
import pandas as pd
from flask import get_flashed_messages
from app import app, db
import os

# Import models and forms from app.py for test setup
from app import User, RegistrationForm, LoginForm, load_user, register, login, logout, index, plot, init_db_command
from sqlalchemy import text
class AuthTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app = app.test_client()
        with app.app_context():
            db.create_all()
    def tearDown(self):
        with app.app_context():
            db.session.execute(text('DELETE FROM user'))
            db.session.commit()
            db.session.remove()

    def test_register(self):
        with app.app_context():
            with self.app as client:
                response = client.post('/register', data={
                    'username': 'testuser',
                    'password': 'password',
                    'confirm_password': 'password'
                }, follow_redirects=True)
                self.assertEqual(response.status_code, 200)
                messages = get_flashed_messages(with_categories=True)
                self.assertIn(('success', 'Your account has been created! You are now able to log in'), messages)

    def test_login_logout(self):
        with app.app_context():
            # First, register a user
            self.app.post('/register', data={
                'username': 'testuser',
                'password': 'password',
                'confirm_password': 'password'
            })
            # Then, log in
            with self.app as client:
                response = client.post('/login', data={
                'username': 'testuser',
                'password': 'password'
            }, follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Stock Price Viewer', response.data)
            # Now, log out
            response = self.app.get('/logout', follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Login', response.data)

    def test_protected_route(self):
        with app.app_context():
            response = self.app.get('/', follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Login', response.data)

    def test_login_unregistered_user(self):
        with app.app_context():
            with self.app as client:
                response = client.post('/login', data={
                    'username': 'nonexistent',
                    'password': 'password'
                }, follow_redirects=True)
                self.assertEqual(response.status_code, 200)
                messages = get_flashed_messages(with_categories=True)
                self.assertIn(('info', 'You are not registered yet. Please sign up.'), messages)

class PlotTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app = app.test_client()
        with app.app_context():
            db.create_all()
            # Create a user
            user = User(username='testuser', password='password')
            db.session.add(user)
            db.session.commit()

    def tearDown(self):
        with app.app_context():
            db.session.execute(text('DELETE FROM user'))
            db.session.commit()
            db.session.remove()

    @patch('yfinance.download')
    def test_plot(self, mock_download):
        with self.app as c:
            with c.session_transaction() as sess:
                sess['_user_id'] = '1'
                sess['_fresh'] = True
        # Create a sample DataFrame to be returned by the mock
        data = {
            'open': [150, 151, 152],
            'high': [155, 156, 157],
            'low': [149, 150, 151],
            'close': [152, 153, 154],
            'volume': [1000, 1100, 1200]
        }
        dates = pd.to_datetime(['2023-01-01', '2023-01-02', '2023-01-03'])
        df = pd.DataFrame(data, index=dates)
        mock_download.return_value = df

        response = self.app.post('/plot', data={
            'ticker': 'AAPL',
            'start_date': '2023-01-01',
            'end_date': '2023-01-03'
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'AAPL Stock Price', response.data)
        self.assertIn(b'<strong>Min Price:</strong> 152.00', response.data)
        self.assertIn(b'<strong>Max Price:</strong> 154.00', response.data)
        self.assertIn(b'<strong>Mean Price:</strong> 153.00', response.data)
        self.assertIn(b'data:image/png;base64,', response.data)
        self.assertIn(b'<table border="1" class="dataframe table table-striped">', response.data)

    @patch('yfinance.download')
    def test_plot_long_range(self, mock_download):
        with self.app as c:
            with c.session_transaction() as sess:
                sess['_user_id'] = '1'
                sess['_fresh'] = True
        # Create a sample DataFrame with 30 days of data
        dates = pd.to_datetime(pd.date_range(start='2023-01-01', periods=30))
        data = {
            'open': [150 + i for i in range(30)],
            'high': [155 + i for i in range(30)],
            'low': [149 + i for i in range(30)],
            'close': [152 + i for i in range(30)],
            'volume': [1000 + i * 10 for i in range(30)]
        }
        df = pd.DataFrame(data, index=dates)
        mock_download.return_value = df

        response = self.app.post('/plot', data={
            'ticker': 'AAPL',
            'start_date': '2023-01-01',
            'end_date': '2023-01-30'
        })

        self.assertEqual(response.status_code, 200)
        # Check that the data is truncated to 20 days
        self.assertNotIn(b'2023-01-01', response.data)
        self.assertIn(b'2023-01-30', response.data)

    @patch('yfinance.download')
    def test_plot_no_data(self, mock_download):
        with self.app as c:
            with c.session_transaction() as sess:
                sess['_user_id'] = '1'
                sess['_fresh'] = True
        # Mock yfinance.download to return an empty DataFrame
        mock_download.return_value = pd.DataFrame()

        response = self.app.post('/plot', data={
            'ticker': 'INVALID',
            'start_date': '2023-01-01',
            'end_date': '2023-01-03'
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<title>Error</title>', response.data)
        self.assertIn(b'No data found for the given ticker and date range.', response.data)
        self.assertIn(b'<a href="/" class="btn btn-primary btn-block">Go Back</a>', response.data)

if __name__ == '__main__':
    unittest.main()
