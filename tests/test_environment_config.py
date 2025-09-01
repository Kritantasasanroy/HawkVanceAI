"""
Unit tests for EnvironmentConfig class.

Tests cover:
- Successful environment loading
- Missing .env file scenarios
- Missing required variables validation
- Error message generation
"""

import unittest
import os
import tempfile
import logging
from pathlib import Path
from unittest.mock import patch, mock_open

# Add the project root to the path
import sys
sys.path.append(str(Path(__file__).parent.parent))

from config.environment import EnvironmentConfig


class TestEnvironmentConfig(unittest.TestCase):
    """Test cases for EnvironmentConfig class."""
    
    def setUp(self):
        """Set up test fixtures before each test method."""
        # Store original environment variables
        self.original_env = {}
        for var in EnvironmentConfig.REQUIRED_VARS:
            self.original_env[var] = os.environ.get(var)
        
        # Clear environment variables for clean testing
        for var in EnvironmentConfig.REQUIRED_VARS:
            if var in os.environ:
                del os.environ[var]
    
    def tearDown(self):
        """Clean up after each test method."""
        # Restore original environment variables
        for var, value in self.original_env.items():
            if value is not None:
                os.environ[var] = value
            elif var in os.environ:
                del os.environ[var]
    
    def test_successful_environment_loading(self):
        """Test successful loading of .env file with all required variables."""
        # Create temporary .env file content
        env_content = """GEMINI_API_KEY=test_api_key_123
TESSERACT_PATH=/usr/bin/tesseract"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as temp_file:
            temp_file.write(env_content)
            temp_file_path = temp_file.name
        
        try:
            # Load environment from temporary file
            EnvironmentConfig.load_environment(temp_file_path)
            
            # Verify variables are loaded
            self.assertEqual(os.getenv('GEMINI_API_KEY'), 'test_api_key_123')
            self.assertEqual(os.getenv('TESSERACT_PATH'), '/usr/bin/tesseract')
            
            # Verify validation passes
            self.assertTrue(EnvironmentConfig.validate_required_vars())
            
        finally:
            # Clean up temporary file
            os.unlink(temp_file_path)
    
    def test_missing_env_file_scenario(self):
        """Test handling of missing .env file."""
        non_existent_file = '/path/that/does/not/exist/.env'
        
        with self.assertLogs(level='WARNING') as log:
            EnvironmentConfig.load_environment(non_existent_file)
            
        # Verify warning message is logged
        self.assertIn('No .env file found', log.output[0])
        self.assertIn('Using system environment variables', log.output[0])
    
    def test_missing_required_variables_validation(self):
        """Test validation failure when required variables are missing."""
        # Ensure no required variables are set
        for var in EnvironmentConfig.REQUIRED_VARS:
            if var in os.environ:
                del os.environ[var]
        
        with self.assertLogs(level='ERROR') as log:
            result = EnvironmentConfig.validate_required_vars()
            
        # Verify validation fails
        self.assertFalse(result)
        
        # Verify error messages are generated
        self.assertTrue(any('CONFIGURATION ERROR: Invalid environment variables' in msg for msg in log.output))
        self.assertTrue(any('GEMINI_API_KEY' in msg for msg in log.output))
        self.assertTrue(any('TESSERACT_PATH' in msg for msg in log.output))
    
    def test_partial_missing_variables(self):
        """Test validation when only some required variables are missing."""
        # Set only one required variable
        os.environ['GEMINI_API_KEY'] = 'test_key'
        # TESSERACT_PATH remains unset
        
        with self.assertLogs(level='ERROR') as log:
            result = EnvironmentConfig.validate_required_vars()
            
        # Verify validation fails
        self.assertFalse(result)
        
        # Verify specific missing variable is mentioned
        self.assertTrue(any('TESSERACT_PATH' in msg for msg in log.output))
        self.assertFalse(any('GEMINI_API_KEY' in msg for msg in log.output))
    
    def test_all_variables_present_validation(self):
        """Test validation success when all required variables are present."""
        # Set all required variables
        os.environ['GEMINI_API_KEY'] = 'test_api_key'
        os.environ['TESSERACT_PATH'] = '/usr/bin/tesseract'
        
        with self.assertLogs(level='INFO') as log:
            result = EnvironmentConfig.validate_required_vars()
            
        # Verify validation passes
        self.assertTrue(result)
        
        # Verify success message is logged
        self.assertTrue(any('All required environment variables are present' in msg for msg in log.output))
    
    def test_get_required_vars(self):
        """Test getting list of required variables."""
        required_vars = EnvironmentConfig.get_required_vars()
        
        # Verify expected variables are returned
        self.assertIn('GEMINI_API_KEY', required_vars)
        self.assertIn('TESSERACT_PATH', required_vars)
        self.assertEqual(len(required_vars), 2)
        
        # Verify it returns a copy (not the original list)
        required_vars.append('TEST_VAR')
        original_vars = EnvironmentConfig.get_required_vars()
        self.assertNotIn('TEST_VAR', original_vars)
    
    def test_get_env_var_with_default(self):
        """Test getting environment variable with default value."""
        # Test with unset variable
        result = EnvironmentConfig.get_env_var('UNSET_VAR', 'default_value')
        self.assertEqual(result, 'default_value')
        
        # Test with set variable
        os.environ['TEST_VAR'] = 'actual_value'
        result = EnvironmentConfig.get_env_var('TEST_VAR', 'default_value')
        self.assertEqual(result, 'actual_value')
        
        # Clean up
        del os.environ['TEST_VAR']
    
    def test_get_env_var_without_default(self):
        """Test getting environment variable without default value."""
        # Test with unset variable
        result = EnvironmentConfig.get_env_var('UNSET_VAR')
        self.assertIsNone(result)
        
        # Test with set variable
        os.environ['TEST_VAR'] = 'actual_value'
        result = EnvironmentConfig.get_env_var('TEST_VAR')
        self.assertEqual(result, 'actual_value')
        
        # Clean up
        del os.environ['TEST_VAR']
    
    def test_is_env_var_set(self):
        """Test checking if environment variable is set."""
        # Test with unset variable
        self.assertFalse(EnvironmentConfig.is_env_var_set('UNSET_VAR'))
        
        # Test with set variable
        os.environ['TEST_VAR'] = 'some_value'
        self.assertTrue(EnvironmentConfig.is_env_var_set('TEST_VAR'))
        
        # Test with empty string (should still be considered set)
        os.environ['EMPTY_VAR'] = ''
        self.assertTrue(EnvironmentConfig.is_env_var_set('EMPTY_VAR'))
        
        # Clean up
        del os.environ['TEST_VAR']
        del os.environ['EMPTY_VAR']
    
    def test_error_message_generation(self):
        """Test that appropriate error messages are generated for different scenarios."""
        # Test missing all variables
        with self.assertLogs(level='ERROR') as log:
            EnvironmentConfig.validate_required_vars()
            
        error_messages = ' '.join(log.output)
        self.assertIn('CONFIGURATION ERROR: Invalid environment variables', error_messages)
        self.assertIn('GEMINI_API_KEY', error_messages)
        self.assertIn('TESSERACT_PATH', error_messages)
        self.assertIn('Create a .env file', error_messages)
    
    def test_empty_variables_validation(self):
        """Test validation failure when required variables are set but empty."""
        # Set variables to empty strings
        os.environ['GEMINI_API_KEY'] = ''
        os.environ['TESSERACT_PATH'] = ''
        
        try:
            with self.assertLogs(level='ERROR') as log:
                result = EnvironmentConfig.validate_required_vars()
                
            # Verify validation fails
            self.assertFalse(result)
            
            # Verify error messages mention empty variables
            error_messages = ' '.join(log.output)
            self.assertIn('Empty variables', error_messages)
            self.assertIn('GEMINI_API_KEY', error_messages)
            self.assertIn('TESSERACT_PATH', error_messages)
            
        finally:
            # Clean up
            del os.environ['GEMINI_API_KEY']
            del os.environ['TESSERACT_PATH']
    
    @patch('config.environment.load_dotenv')
    @patch('os.path.exists')
    def test_load_environment_calls_load_dotenv(self, mock_exists, mock_load_dotenv):
        """Test that load_environment properly calls load_dotenv when file exists."""
        mock_exists.return_value = True
        
        test_file = '/test/path/.env'
        EnvironmentConfig.load_environment(test_file)
        
        mock_load_dotenv.assert_called_once_with(test_file)
    
    def test_default_env_file_path(self):
        """Test that default .env file path is correctly determined."""
        with patch('os.path.exists') as mock_exists, \
             patch('config.environment.load_dotenv') as mock_load_dotenv:
            
            mock_exists.return_value = True
            
            # Call without specifying env_file
            EnvironmentConfig.load_environment()
            
            # Verify load_dotenv was called with a path ending in .env
            call_args = mock_load_dotenv.call_args[0][0]
            self.assertTrue(str(call_args).endswith('.env'))


if __name__ == '__main__':
    # Configure logging for tests
    logging.basicConfig(level=logging.DEBUG)
    
    # Run the tests
    unittest.main()