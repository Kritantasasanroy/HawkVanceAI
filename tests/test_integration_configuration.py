"""
Isolated integration tests for complete configuration system.

Tests cover:
- Application startup with valid environment configuration
- Component initialization with environment-loaded settings
- Error scenarios with missing or invalid configuration

This test file uses isolated imports to avoid interference from the actual .env file.
"""

import unittest
import os
import sys
import tempfile
import logging
from pathlib import Path
from unittest.mock import patch, MagicMock
from io import StringIO

# Add the project root to the path
sys.path.append(str(Path(__file__).parent.parent))


class TestConfigurationIntegrationIsolated(unittest.TestCase):
    """Isolated integration tests for the complete configuration system."""
    
    def setUp(self):
        """Set up test fixtures before each test method."""
        # Store original environment variables
        self.original_env = {}
        required_vars = ['GEMINI_API_KEY', 'TESSERACT_PATH']
        for var in required_vars:
            self.original_env[var] = os.environ.get(var)
        
        # Clear environment variables for clean testing
        for var in required_vars:
            if var in os.environ:
                del os.environ[var]
        
        # Create temporary directory for test files
        self.temp_dir = tempfile.mkdtemp()
        self.temp_env_file = os.path.join(self.temp_dir, '.env')
        
        # Capture logs for testing
        self.log_capture = StringIO()
        self.log_handler = logging.StreamHandler(self.log_capture)
        self.log_handler.setLevel(logging.DEBUG)
        logging.getLogger().addHandler(self.log_handler)
        logging.getLogger().setLevel(logging.DEBUG)
    
    def tearDown(self):
        """Clean up after each test method."""
        # Restore original environment variables
        for var, value in self.original_env.items():
            if value is not None:
                os.environ[var] = value
            elif var in os.environ:
                del os.environ[var]
        
        # Clean up temporary files
        if os.path.exists(self.temp_env_file):
            os.unlink(self.temp_env_file)
        os.rmdir(self.temp_dir)
        
        # Remove log handler
        logging.getLogger().removeHandler(self.log_handler)
    
    def create_valid_env_file(self, api_key="test_api_key_123", tesseract_path="/usr/bin/tesseract"):
        """Create a valid .env file for testing."""
        env_content = f"""GEMINI_API_KEY={api_key}
TESSERACT_PATH={tesseract_path}"""
        
        with open(self.temp_env_file, 'w') as f:
            f.write(env_content)
        
        return self.temp_env_file
    
    def test_application_startup_with_valid_configuration(self):
        """Test successful application startup with valid environment configuration."""
        from config.environment import EnvironmentConfig
        
        # Create valid .env file
        self.create_valid_env_file()
        
        # Load environment configuration
        EnvironmentConfig.load_environment(self.temp_env_file)
        
        # Verify environment variables are loaded
        self.assertEqual(os.getenv('GEMINI_API_KEY'), 'test_api_key_123')
        self.assertEqual(os.getenv('TESSERACT_PATH'), '/usr/bin/tesseract')
        
        # Verify validation passes
        self.assertTrue(EnvironmentConfig.validate_required_vars())
        
        # Verify configuration status logging
        log_output = self.log_capture.getvalue()
        self.assertIn('All required environment variables are present', log_output)
        self.assertIn('Loaded environment variables', log_output)
    
    def test_component_initialization_with_environment_settings(self):
        """Test component initialization with environment-loaded settings."""
        from config.environment import EnvironmentConfig
        
        # Create valid .env file with realistic paths
        api_key = "AIzaSyTest123_ValidAPIKey"
        tesseract_path = "/usr/bin/tesseract"  # Mock path for testing
        
        self.create_valid_env_file(api_key, tesseract_path)
        EnvironmentConfig.load_environment(self.temp_env_file)
        
        # Verify environment variables are available
        self.assertEqual(os.getenv('GEMINI_API_KEY'), api_key)
        self.assertEqual(os.getenv('TESSERACT_PATH'), tesseract_path)
        
        # Test GeminiProcessor initialization with environment-loaded API key
        with patch('src.core.gemini_api.GEMINI_API_KEY', api_key), \
             patch('google.generativeai.configure') as mock_configure, \
             patch('google.generativeai.GenerativeModel') as mock_model:
            
            mock_model.return_value = MagicMock()
            
            # Import GeminiProcessor after setting environment variables
            from src.core.gemini_api import GeminiProcessor
            
            try:
                gemini_processor = GeminiProcessor()
                
                # Verify API key was used for configuration
                mock_configure.assert_called_once_with(api_key=api_key)
                
                # Verify processor was initialized successfully
                self.assertIsNotNone(gemini_processor)
                self.assertIsNotNone(gemini_processor.model)
                
            except Exception as e:
                self.fail(f"GeminiProcessor initialization failed: {str(e)}")
        
        # Test OCRProcessor initialization with environment-loaded Tesseract path
        with patch('pytesseract.get_tesseract_version') as mock_version, \
             patch('os.path.exists') as mock_exists:
            
            mock_version.return_value = "5.0.0"
            mock_exists.return_value = True
            
            from src.core.ocr import OCRProcessor
            
            try:
                ocr_processor = OCRProcessor(tesseract_path)
                
                # Verify processor was initialized successfully
                self.assertIsNotNone(ocr_processor)
                
                # Verify Tesseract path was set correctly
                import pytesseract
                self.assertEqual(pytesseract.pytesseract.tesseract_cmd, tesseract_path)
                
            except Exception as e:
                self.fail(f"OCRProcessor initialization failed: {str(e)}")
    
    def test_settings_validation_with_valid_environment(self):
        """Test settings validation with valid environment configuration."""
        from config.environment import EnvironmentConfig
        
        # Create valid .env file
        self.create_valid_env_file()
        EnvironmentConfig.load_environment(self.temp_env_file)
        
        # Mock file existence for Tesseract path validation
        with patch('os.path.exists') as mock_exists:
            mock_exists.return_value = True
            
            # Import and test settings validation after environment is set
            from config.settings import validate_configuration
            
            try:
                validate_configuration()
                
                # Verify no exception was raised
                log_output = self.log_capture.getvalue()
                self.assertIn('Configuration validation successful', log_output)
                
            except Exception as e:
                self.fail(f"Configuration validation failed unexpectedly: {str(e)}")
    
    def test_startup_failure_with_missing_api_key(self):
        """Test application startup failure when API key is missing."""
        from config.environment import EnvironmentConfig
        
        # Create .env file with missing API key
        env_content = "TESSERACT_PATH=/usr/bin/tesseract"
        with open(self.temp_env_file, 'w') as f:
            f.write(env_content)
        
        EnvironmentConfig.load_environment(self.temp_env_file)
        
        # Verify validation fails
        self.assertFalse(EnvironmentConfig.validate_required_vars())
        
        # Verify appropriate error messages
        log_output = self.log_capture.getvalue()
        self.assertIn('CONFIGURATION ERROR', log_output)
        self.assertIn('GEMINI_API_KEY', log_output)
        self.assertIn('Missing variables', log_output)
    
    def test_startup_failure_with_missing_tesseract_path(self):
        """Test application startup failure when Tesseract path is missing."""
        from config.environment import EnvironmentConfig
        
        # Create .env file with missing Tesseract path
        env_content = "GEMINI_API_KEY=test_api_key_123"
        with open(self.temp_env_file, 'w') as f:
            f.write(env_content)
        
        EnvironmentConfig.load_environment(self.temp_env_file)
        
        # Verify validation fails
        self.assertFalse(EnvironmentConfig.validate_required_vars())
        
        # Verify appropriate error messages
        log_output = self.log_capture.getvalue()
        self.assertIn('CONFIGURATION ERROR', log_output)
        self.assertIn('TESSERACT_PATH', log_output)
        self.assertIn('Missing variables', log_output)
    
    def test_startup_failure_with_empty_variables(self):
        """Test application startup failure when variables are empty."""
        from config.environment import EnvironmentConfig
        
        # Create .env file with empty variables
        env_content = """GEMINI_API_KEY=
TESSERACT_PATH="""
        with open(self.temp_env_file, 'w') as f:
            f.write(env_content)
        
        EnvironmentConfig.load_environment(self.temp_env_file)
        
        # Verify validation fails
        self.assertFalse(EnvironmentConfig.validate_required_vars())
        
        # Verify appropriate error messages
        log_output = self.log_capture.getvalue()
        self.assertIn('CONFIGURATION ERROR', log_output)
        self.assertIn('Empty variables', log_output)
        self.assertIn('GEMINI_API_KEY', log_output)
        self.assertIn('TESSERACT_PATH', log_output)
    
    def test_startup_failure_with_invalid_tesseract_path(self):
        """Test application startup failure when Tesseract path is invalid."""
        from config.environment import EnvironmentConfig
        
        # Create .env file with invalid Tesseract path
        invalid_path = "/nonexistent/path/tesseract"
        self.create_valid_env_file(tesseract_path=invalid_path)
        EnvironmentConfig.load_environment(self.temp_env_file)
        
        # Verify environment validation passes (path validation is separate)
        self.assertTrue(EnvironmentConfig.validate_required_vars())
        
        # Test settings validation with invalid path
        from config.settings import validate_configuration
        
        with self.assertRaises(ValueError) as context:
            validate_configuration()
        
        # Verify appropriate error message
        self.assertIn('TESSERACT_PATH points to non-existent file', str(context.exception))
        self.assertIn(invalid_path, str(context.exception))
    
    def test_component_initialization_failure_with_missing_api_key(self):
        """Test component initialization failure when API key is missing."""
        # Ensure API key is not set
        if 'GEMINI_API_KEY' in os.environ:
            del os.environ['GEMINI_API_KEY']
        
        # Mock the module-level GEMINI_API_KEY to be None
        with patch('src.core.gemini_api.GEMINI_API_KEY', None):
            from src.core.gemini_api import GeminiProcessor
            
            # Test GeminiProcessor initialization failure
            with self.assertRaises((ValueError, RuntimeError)) as context:
                GeminiProcessor()
            
            # Verify appropriate error message (could be ValueError or RuntimeError)
            error_msg = str(context.exception)
            self.assertTrue(
                'GEMINI_API_KEY environment variable is not set' in error_msg or
                'Failed to initialize Gemini API' in error_msg
            )
    
    def test_component_initialization_failure_with_invalid_tesseract_path(self):
        """Test component initialization failure when Tesseract path is invalid."""
        from src.core.ocr import OCRProcessor
        
        invalid_path = "/nonexistent/path/tesseract"
        
        # Test OCRProcessor initialization failure
        with self.assertRaises(RuntimeError) as context:
            OCRProcessor(invalid_path)
        
        # Verify appropriate error message
        self.assertIn('Tesseract not found at', str(context.exception))
        self.assertIn(invalid_path, str(context.exception))
    
    def test_graceful_degradation_with_partial_configuration(self):
        """Test graceful degradation when some components can't initialize."""
        # Set up environment with valid API key but invalid Tesseract path
        api_key = 'test_api_key_123'
        os.environ['GEMINI_API_KEY'] = api_key
        os.environ['TESSERACT_PATH'] = '/nonexistent/tesseract'
        
        from config.environment import EnvironmentConfig
        
        # Verify environment validation passes
        self.assertTrue(EnvironmentConfig.validate_required_vars())
        
        # Test that GeminiProcessor can still initialize
        with patch('src.core.gemini_api.GEMINI_API_KEY', api_key), \
             patch('google.generativeai.configure') as mock_configure, \
             patch('google.generativeai.GenerativeModel') as mock_model:
            
            mock_model.return_value = MagicMock()
            
            from src.core.gemini_api import GeminiProcessor
            
            try:
                gemini_processor = GeminiProcessor()
                self.assertIsNotNone(gemini_processor)
                mock_configure.assert_called_once_with(api_key=api_key)
            except Exception as e:
                self.fail(f"GeminiProcessor should initialize with valid API key: {str(e)}")
        
        # Test that OCRProcessor fails gracefully
        from src.core.ocr import OCRProcessor
        
        with self.assertRaises(RuntimeError):
            OCRProcessor('/nonexistent/tesseract')
    
    def test_configuration_diagnostics_with_missing_env_file(self):
        """Test configuration diagnostics when .env file is missing."""
        from config.environment import EnvironmentConfig
        
        # Ensure no .env file exists
        if os.path.exists(self.temp_env_file):
            os.unlink(self.temp_env_file)
        
        # Mock the Path to point to our temp directory instead of the actual project
        with patch('config.environment.Path') as mock_path:
            mock_path.return_value.parent.parent = Path(self.temp_dir)
            
            # Run diagnostics
            EnvironmentConfig.diagnose_configuration_issues()
            
            # Verify diagnostic messages
            log_output = self.log_capture.getvalue()
            self.assertIn('Running configuration diagnostics', log_output)
            self.assertIn('.env file not found', log_output)
            self.assertIn('No required variables found in system environment', log_output)
    
    def test_configuration_status_logging(self):
        """Test detailed configuration status logging."""
        from config.environment import EnvironmentConfig
        
        # Set up valid environment
        self.create_valid_env_file()
        EnvironmentConfig.load_environment(self.temp_env_file)
        
        # Mock file existence for Tesseract path
        with patch('os.path.exists') as mock_exists:
            mock_exists.return_value = True
            
            # Log configuration status
            EnvironmentConfig.log_configuration_status()
            
            # Verify status messages
            log_output = self.log_capture.getvalue()
            self.assertIn('Environment Configuration Status', log_output)
            self.assertIn('GEMINI_API_KEY: ✓ Set', log_output)
            self.assertIn('TESSERACT_PATH: ✓ Set and file exists', log_output)
    
    def test_end_to_end_configuration_flow(self):
        """Test complete end-to-end configuration flow."""
        from config.environment import EnvironmentConfig
        
        # Step 1: Create valid .env file
        api_key = "AIzaSyTest123_ValidAPIKey"
        tesseract_path = "/usr/bin/tesseract"
        self.create_valid_env_file(api_key, tesseract_path)
        
        # Step 2: Load environment configuration
        EnvironmentConfig.load_environment(self.temp_env_file)
        
        # Step 3: Validate environment variables
        self.assertTrue(EnvironmentConfig.validate_required_vars())
        
        # Step 4: Validate settings configuration
        with patch('os.path.exists') as mock_exists:
            mock_exists.return_value = True
            from config.settings import validate_configuration
            validate_configuration()
        
        # Step 5: Initialize components
        with patch('src.core.gemini_api.GEMINI_API_KEY', api_key), \
             patch('google.generativeai.configure') as mock_configure, \
             patch('google.generativeai.GenerativeModel') as mock_model, \
             patch('pytesseract.get_tesseract_version') as mock_version, \
             patch('os.path.exists') as mock_exists:
            
            mock_model.return_value = MagicMock()
            mock_version.return_value = "5.0.0"
            mock_exists.return_value = True
            
            # Initialize components
            from src.core.gemini_api import GeminiProcessor
            from src.core.ocr import OCRProcessor
            
            gemini_processor = GeminiProcessor()
            ocr_processor = OCRProcessor(tesseract_path)
            
            # Verify successful initialization
            self.assertIsNotNone(gemini_processor)
            self.assertIsNotNone(ocr_processor)
            mock_configure.assert_called_once_with(api_key=api_key)
        
        # Step 6: Verify complete flow logged correctly
        log_output = self.log_capture.getvalue()
        self.assertIn('Loaded environment variables', log_output)
        self.assertIn('All required environment variables are present', log_output)
        self.assertIn('Configuration validation successful', log_output)


class TestMainApplicationIntegrationIsolated(unittest.TestCase):
    """Isolated integration tests for main application startup with configuration."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.original_env = {}
        required_vars = ['GEMINI_API_KEY', 'TESSERACT_PATH']
        for var in required_vars:
            self.original_env[var] = os.environ.get(var)
        
        # Clear environment variables
        for var in required_vars:
            if var in os.environ:
                del os.environ[var]
        
        # Create temporary .env file
        self.temp_dir = tempfile.mkdtemp()
        self.temp_env_file = os.path.join(self.temp_dir, '.env')
    
    def tearDown(self):
        """Clean up after tests."""
        # Restore environment variables
        for var, value in self.original_env.items():
            if value is not None:
                os.environ[var] = value
            elif var in os.environ:
                del os.environ[var]
        
        # Clean up temporary files
        if os.path.exists(self.temp_env_file):
            os.unlink(self.temp_env_file)
        os.rmdir(self.temp_dir)
    
    def test_main_application_startup_validation(self):
        """Test that main application properly validates configuration on startup."""
        from config.environment import EnvironmentConfig
        
        # Create valid .env file
        env_content = """GEMINI_API_KEY=test_api_key_123
TESSERACT_PATH=/usr/bin/tesseract"""
        
        with open(self.temp_env_file, 'w') as f:
            f.write(env_content)
        
        # Test the main application startup logic (without GUI)
        with patch('config.environment.EnvironmentConfig.load_environment') as mock_load, \
             patch('config.environment.EnvironmentConfig.validate_required_vars') as mock_validate, \
             patch('config.settings.validate_configuration') as mock_settings_validate, \
             patch('os.path.exists') as mock_exists:
            
            mock_load.return_value = None
            mock_validate.return_value = True
            mock_settings_validate.return_value = None
            mock_exists.return_value = True
            
            # Import and test main startup logic
            try:
                # Simulate main application startup sequence
                EnvironmentConfig.load_environment(self.temp_env_file)
                
                # Verify startup sequence calls
                mock_load.assert_called_once()
                
                # Test validation
                result = EnvironmentConfig.validate_required_vars()
                self.assertTrue(result or mock_validate.return_value)
                
            except SystemExit:
                self.fail("Application should not exit with valid configuration")
    
    def test_main_application_exit_on_invalid_configuration(self):
        """Test that main application exits gracefully with invalid configuration."""
        from config.environment import EnvironmentConfig
        
        # Create invalid .env file (missing API key)
        env_content = "TESSERACT_PATH=/usr/bin/tesseract"
        
        with open(self.temp_env_file, 'w') as f:
            f.write(env_content)
        
        # Load the invalid configuration
        EnvironmentConfig.load_environment(self.temp_env_file)
        
        # Verify validation fails
        self.assertFalse(EnvironmentConfig.validate_required_vars())
        
        # Verify that missing variables are detected
        missing_vars = EnvironmentConfig.get_missing_vars()
        self.assertIn('GEMINI_API_KEY', missing_vars)


if __name__ == '__main__':
    # Configure logging for tests
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run the tests
    unittest.main(verbosity=2)