"""
Environment Configuration Manager

This module handles loading and validation of environment variables
from .env files using python-dotenv library.
"""

import os
import logging
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv


class EnvironmentConfig:
    """Manages environment variable loading and validation."""
    
    # Required environment variables for the application
    REQUIRED_VARS = [
        'GEMINI_API_KEY',
        'TESSERACT_PATH'
    ]
    
    @staticmethod
    def load_environment(env_file: Optional[str] = None) -> None:
        """
        Load environment variables from .env file.
        
        Args:
            env_file: Optional path to .env file. If None, looks for .env in current directory.
        """
        if env_file is None:
            # Look for .env file in the same directory as this module
            current_dir = Path(__file__).parent.parent
            env_file = current_dir / '.env'
        
        if os.path.exists(env_file):
            load_dotenv(env_file)
            logging.info(f"Loaded environment variables from {env_file}")
        else:
            logging.warning(f"No .env file found at {env_file}. Using system environment variables.")
    
    @staticmethod
    def validate_required_vars() -> bool:
        """
        Validate that all required environment variables are present.
        
        Returns:
            bool: True if all required variables are present, False otherwise.
        """
        missing_vars = []
        empty_vars = []
        
        for var in EnvironmentConfig.REQUIRED_VARS:
            value = os.getenv(var)
            if value is None:
                missing_vars.append(var)
            elif value.strip() == "":
                empty_vars.append(var)
        
        if missing_vars or empty_vars:
            logging.error("=" * 60)
            logging.error("CONFIGURATION ERROR: Invalid environment variables")
            logging.error("=" * 60)
            
            if missing_vars:
                logging.error(f"Missing variables: {', '.join(missing_vars)}")
                logging.error("These variables are not set in your environment or .env file.")
                logging.error("")
            
            if empty_vars:
                logging.error(f"Empty variables: {', '.join(empty_vars)}")
                logging.error("These variables are set but contain empty values.")
                logging.error("")
            
            logging.error("RESOLUTION STEPS:")
            logging.error("1. Create a .env file in the HawkVanceAI directory")
            logging.error("2. Copy .env.example to .env if it exists")
            logging.error("3. Add the following variables to your .env file:")
            
            all_invalid_vars = missing_vars + empty_vars
            for var in all_invalid_vars:
                if var == 'GEMINI_API_KEY':
                    logging.error(f"   {var}=your_actual_gemini_api_key_here")
                    logging.error("     (Get your API key from https://makersuite.google.com/app/apikey)")
                elif var == 'TESSERACT_PATH':
                    logging.error(f"   {var}=C:\\Users\\username\\AppData\\Local\\Programs\\Tesseract-OCR\\tesseract.exe")
                    logging.error("     (Adjust path to match your Tesseract installation)")
                else:
                    logging.error(f"   {var}=your_value_here")
            
            logging.error("")
            logging.error("ALTERNATIVE: Set these variables in your system environment")
            logging.error("Windows: setx VARIABLE_NAME \"value\"")
            logging.error("Linux/Mac: export VARIABLE_NAME=\"value\"")
            logging.error("")
            logging.error("For troubleshooting help, check the application documentation.")
            logging.error("=" * 60)
            return False
        
        logging.info("✓ All required environment variables are present and valid.")
        return True
    
    @staticmethod
    def get_required_vars() -> List[str]:
        """
        Get list of required environment variables.
        
        Returns:
            List[str]: List of required environment variable names.
        """
        return EnvironmentConfig.REQUIRED_VARS.copy()
    
    @staticmethod
    def get_env_var(var_name: str, default: Optional[str] = None) -> Optional[str]:
        """
        Get environment variable value with optional default.
        
        Args:
            var_name: Name of the environment variable
            default: Default value if variable is not found
            
        Returns:
            str or None: Environment variable value or default
        """
        return os.getenv(var_name, default)
    
    @staticmethod
    def is_env_var_set(var_name: str) -> bool:
        """
        Check if an environment variable is set.
        
        Args:
            var_name: Name of the environment variable
            
        Returns:
            bool: True if variable is set, False otherwise
        """
        return os.getenv(var_name) is not None
    
    @staticmethod
    def get_missing_vars() -> List[str]:
        """
        Get list of missing required environment variables.
        
        Returns:
            List[str]: List of missing required environment variable names.
        """
        missing_vars = []
        for var in EnvironmentConfig.REQUIRED_VARS:
            if not os.getenv(var):
                missing_vars.append(var)
        return missing_vars
    
    @staticmethod
    def log_configuration_status() -> None:
        """
        Log detailed configuration status for debugging.
        """
        logging.info("Environment Configuration Status:")
        for var in EnvironmentConfig.REQUIRED_VARS:
            value = os.getenv(var)
            if value and value.strip():
                # Don't log the actual value for security reasons
                if var == 'GEMINI_API_KEY':
                    logging.info(f"  {var}: ✓ Set (length: {len(value)} characters)")
                elif var == 'TESSERACT_PATH':
                    # For paths, we can check if the file exists
                    if os.path.exists(value):
                        logging.info(f"  {var}: ✓ Set and file exists")
                    else:
                        logging.warning(f"  {var}: ⚠ Set but file not found at: {value}")
                else:
                    logging.info(f"  {var}: ✓ Set")
            elif value == "":
                logging.error(f"  {var}: ✗ Empty value")
            else:
                logging.error(f"  {var}: ✗ Missing")
    
    @staticmethod
    def diagnose_configuration_issues() -> None:
        """
        Provide detailed diagnostics for configuration issues.
        """
        logging.info("Running configuration diagnostics...")
        
        # Check if .env file exists
        current_dir = Path(__file__).parent.parent
        env_file = current_dir / '.env'
        env_example_file = current_dir / '.env.example'
        
        if env_file.exists():
            logging.info(f"✓ .env file found at: {env_file}")
        else:
            logging.warning(f"⚠ .env file not found at: {env_file}")
            if env_example_file.exists():
                logging.info(f"ℹ .env.example file available at: {env_example_file}")
                logging.info("  You can copy this file to .env and update the values")
            else:
                logging.warning("⚠ No .env.example file found")
        
        # Check system environment variables
        logging.info("Checking system environment variables...")
        system_vars_found = []
        for var in EnvironmentConfig.REQUIRED_VARS:
            if var in os.environ:
                system_vars_found.append(var)
        
        if system_vars_found:
            logging.info(f"✓ Found in system environment: {', '.join(system_vars_found)}")
        else:
            logging.info("ℹ No required variables found in system environment")
        
        # Provide specific guidance
        missing_vars = EnvironmentConfig.get_missing_vars()
        if missing_vars:
            logging.info("Configuration guidance:")
            for var in missing_vars:
                if var == 'GEMINI_API_KEY':
                    logging.info(f"  {var}: Obtain from Google AI Studio (https://makersuite.google.com/app/apikey)")
                elif var == 'TESSERACT_PATH':
                    logging.info(f"  {var}: Install Tesseract OCR and provide the executable path")
                    logging.info("    Windows: Usually C:\\Program Files\\Tesseract-OCR\\tesseract.exe")
                    logging.info("    Linux: Usually /usr/bin/tesseract")
                    logging.info("    Mac: Usually /usr/local/bin/tesseract")