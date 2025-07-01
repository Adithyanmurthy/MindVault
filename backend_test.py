import unittest
import requests
import json
import random
import string
import time
import os
from dotenv import load_dotenv

# Load environment variables from frontend/.env to get the backend URL
load_dotenv('/app/frontend/.env')
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL')
API_URL = f"{BASE_URL}/api"

def random_string(length=8):
    """Generate a random string for test data"""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

class TestMindVaultAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up test data that will be used across all tests"""
        cls.test_user = {
            "email": f"test_{random_string()}@example.com",
            "username": f"testuser_{random_string()}",
            "password": "SecurePassword123!"
        }
        cls.auth_token = None
        cls.user_id = None
        cls.created_ideas = []
        
        print(f"Using API URL: {API_URL}")
        
    def test_01_server_health(self):
        """Test if the server is running"""
        response = requests.get(f"{BASE_URL}/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("message", data)
        self.assertIn("MindVault API is running", data["message"])
        print("✅ Server health check passed")
        
    def test_02_user_registration(self):
        """Test user registration endpoint"""
        url = f"{API_URL}/auth/register"
        response = requests.post(url, json=self.test_user)
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Verify response structure
        self.assertIn("access_token", data)
        self.assertIn("token_type", data)
        self.assertIn("user", data)
        self.assertEqual(data["token_type"], "bearer")
        
        # Store token and user ID for subsequent tests
        self.__class__.auth_token = data["access_token"]
        self.__class__.user_id = data["user"]["id"]
        
        print(f"✅ User registration successful: {self.test_user['email']}")
        
    def test_03_user_login(self):
        """Test user login endpoint"""
        url = f"{API_URL}/auth/login"
        login_data = {
            "email": self.test_user["email"],
            "password": self.test_user["password"]
        }
        
        response = requests.post(url, json=login_data)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Verify response structure
        self.assertIn("access_token", data)
        self.assertIn("token_type", data)
        self.assertIn("user", data)
        self.assertEqual(data["token_type"], "bearer")
        
        # Update token
        self.__class__.auth_token = data["access_token"]
        
        print(f"✅ User login successful: {self.test_user['email']}")
        
    def test_04_get_current_user(self):
        """Test get current user endpoint"""
        url = f"{API_URL}/auth/me"
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        response = requests.get(url, headers=headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Verify user data
        self.assertEqual(data["id"], self.user_id)
        self.assertEqual(data["email"], self.test_user["email"])
        self.assertEqual(data["username"], self.test_user["username"])
        
        print("✅ Get current user successful")
        
    def test_05_create_idea(self):
        """Test idea creation endpoint"""
        url = f"{API_URL}/ideas"
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        # Create three different ideas with different priorities and tags
        ideas = [
            {
                "title": "Revolutionary App Idea",
                "content": "Create an app that uses AI to predict market trends and suggest investment opportunities.",
                "tags": ["technology", "finance", "ai"],
                "priority": "high",
                "category": "product"
            },
            {
                "title": "Novel Plot Concept",
                "content": "A story about a detective who can see through the eyes of criminals but only when they're committing crimes.",
                "tags": ["fiction", "thriller", "writing"],
                "priority": "medium",
                "category": "story"
            },
            {
                "title": "Healthy Lifestyle Plan",
                "content": "Develop a 30-day plan that combines intermittent fasting, meditation, and progressive exercise.",
                "tags": ["health", "wellness", "personal"],
                "priority": "low"
            }
        ]
        
        for idea in ideas:
            response = requests.post(url, json=idea, headers=headers)
            self.assertEqual(response.status_code, 200)
            data = response.json()
            
            # Verify idea data
            self.assertIn("id", data)
            self.assertEqual(data["title"], idea["title"])
            self.assertEqual(data["content"], idea["content"])
            self.assertEqual(data["tags"], idea["tags"])
            self.assertEqual(data["priority"], idea["priority"])
            if "category" in idea:
                self.assertEqual(data["category"], idea["category"])
            
            # Store idea ID for later tests
            self.__class__.created_ideas.append(data["id"])
            
        print(f"✅ Created {len(ideas)} ideas successfully")
        
    def test_06_get_all_ideas(self):
        """Test get all ideas endpoint"""
        url = f"{API_URL}/ideas"
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        response = requests.get(url, headers=headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Verify we get at least the ideas we created
        self.assertGreaterEqual(len(data), len(self.created_ideas))
        
        # Verify idea structure
        for idea in data:
            self.assertIn("id", idea)
            self.assertIn("title", idea)
            self.assertIn("content", idea)
            self.assertIn("tags", idea)
            self.assertIn("priority", idea)
            
        print(f"✅ Retrieved {len(data)} ideas successfully")
        
    def test_07_filter_ideas_by_tag(self):
        """Test filtering ideas by tag"""
        tag = "technology"
        url = f"{API_URL}/ideas?tag={tag}"
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        response = requests.get(url, headers=headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Verify all returned ideas have the specified tag
        for idea in data:
            self.assertIn(tag, idea["tags"])
            
        print(f"✅ Filtered ideas by tag '{tag}' successfully")
        
    def test_08_filter_ideas_by_priority(self):
        """Test filtering ideas by priority"""
        priority = "high"
        url = f"{API_URL}/ideas?priority={priority}"
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        response = requests.get(url, headers=headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Verify all returned ideas have the specified priority
        for idea in data:
            self.assertEqual(idea["priority"], priority)
            
        print(f"✅ Filtered ideas by priority '{priority}' successfully")
        
    def test_09_filter_ideas_by_category(self):
        """Test filtering ideas by category"""
        category = "product"
        url = f"{API_URL}/ideas?category={category}"
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        response = requests.get(url, headers=headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Verify all returned ideas have the specified category
        for idea in data:
            self.assertEqual(idea["category"], category)
            
        print(f"✅ Filtered ideas by category '{category}' successfully")
        
    def test_10_get_single_idea(self):
        """Test getting a single idea by ID"""
        idea_id = self.created_ideas[0]
        url = f"{API_URL}/ideas/{idea_id}"
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        response = requests.get(url, headers=headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Verify idea data
        self.assertEqual(data["id"], idea_id)
        
        print(f"✅ Retrieved single idea successfully")
        
    def test_11_update_idea(self):
        """Test updating an idea"""
        idea_id = self.created_ideas[0]
        url = f"{API_URL}/ideas/{idea_id}"
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        update_data = {
            "title": "Updated Idea Title",
            "content": "This content has been updated for testing purposes.",
            "is_favorite": True
        }
        
        response = requests.put(url, json=update_data, headers=headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Verify updated data
        self.assertEqual(data["title"], update_data["title"])
        self.assertEqual(data["content"], update_data["content"])
        self.assertEqual(data["is_favorite"], update_data["is_favorite"])
        
        print(f"✅ Updated idea successfully")
        
    def test_12_smart_suggestions(self):
        """Test getting smart suggestions for an idea"""
        idea_id = self.created_ideas[1]  # Use the second idea
        url = f"{API_URL}/ideas/{idea_id}/suggestions"
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        response = requests.post(url, headers=headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Verify suggestion structure
        self.assertIn("type", data)
        self.assertIn("suggestions", data)
        self.assertIn("confidence", data)
        self.assertEqual(data["type"], "tag")
        self.assertIsInstance(data["suggestions"], list)
        
        print(f"✅ Got smart suggestions successfully: {data['suggestions']}")
        
    def test_13_combine_ideas(self):
        """Test combining two ideas"""
        if len(self.created_ideas) >= 2:
            url = f"{API_URL}/ideas/combine"
            headers = {"Authorization": f"Bearer {self.auth_token}"}
            
            combine_data = {
                "idea1_id": self.created_ideas[0],
                "idea2_id": self.created_ideas[1],
                "new_title": "Combined Brilliant Concept"
            }
            
            response = requests.post(url, json=combine_data, headers=headers)
            self.assertEqual(response.status_code, 200)
            data = response.json()
            
            # Verify combined idea
            self.assertEqual(data["title"], combine_data["new_title"])
            self.assertEqual(data["category"], "fusion")
            self.assertIn("Fusion of Ideas", data["content"])
            
            # Store the combined idea ID
            self.__class__.created_ideas.append(data["id"])
            
            print(f"✅ Combined ideas successfully")
        else:
            self.skipTest("Not enough ideas to combine")
        
    def test_14_analytics_dashboard(self):
        """Test getting analytics dashboard data"""
        url = f"{API_URL}/analytics/dashboard"
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        response = requests.get(url, headers=headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Verify dashboard structure
        self.assertIn("total_ideas", data)
        self.assertIn("priority_breakdown", data)
        self.assertIn("category_breakdown", data)
        self.assertIn("recent_activity", data)
        self.assertIn("favorite_count", data)
        
        # Verify we have the expected number of ideas
        self.assertGreaterEqual(data["total_ideas"], len(self.created_ideas))
        
        print(f"✅ Retrieved analytics dashboard successfully")
        
    def test_15_delete_idea(self):
        """Test deleting an idea"""
        idea_id = self.created_ideas[0]
        url = f"{API_URL}/ideas/{idea_id}"
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        response = requests.delete(url, headers=headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Verify deletion message
        self.assertIn("message", data)
        self.assertIn("deleted successfully", data["message"])
        
        # Verify idea is actually deleted
        response = requests.get(url, headers=headers)
        self.assertEqual(response.status_code, 404)
        
        print(f"✅ Deleted idea successfully")
        
    def test_16_error_handling(self):
        """Test error handling for various scenarios"""
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        # Test invalid idea ID
        response = requests.get(f"{API_URL}/ideas/invalid-id", headers=headers)
        self.assertEqual(response.status_code, 404)
        
        # Test invalid authentication
        response = requests.get(f"{API_URL}/ideas", headers={"Authorization": "Bearer invalid-token"})
        self.assertEqual(response.status_code, 401)
        
        # Test duplicate email registration
        response = requests.post(f"{API_URL}/auth/register", json=self.test_user)
        self.assertEqual(response.status_code, 400)
        
        print(f"✅ Error handling tests passed")

if __name__ == "__main__":
    # Run the tests in order
    unittest.main(argv=['first-arg-is-ignored'], exit=False)