"""
Base Service Class - Abstract interface for all services

All services inherit from BaseService and implement execute() method.
Returns dict-based structures for flexibility (can be converted to Pydantic DTO later).
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime

class BaseService(ABC):
    """
    Abstract base class for all services.
    
    Each service implements the execute() method which takes a dict input
    and returns a dict output.
    
    Future: Can be easily adapted to return Pydantic models instead of dicts.
    """

    def __init__(self):
        """Initialize service"""
        self.created_at = datetime.now()

    @abstractmethod
    def execute(self, *args, **kwargs) -> Dict[str, Any]:
        """
        Execute the service logic.
        
        Args:
            *args: Positional arguments (varies by service)
            **kwargs: Keyword arguments (varies by service)
        
        Returns:
            dict: Service output in dict format
        
        Raises:
            ServiceError: Custom exception if execution fails
        """
        pass

    def validate_input(self, data: Any) -> bool:
        """
        Validate input data before processing.
        
        Args:
            data: Input data to validate
        
        Returns:
            bool: True if valid, raises exception if invalid
        """
        raise NotImplementedError("Subclass must implement validate_input()")

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(created_at={self.created_at})"


class ServiceError(Exception):
    """Base exception for all service errors"""
    pass

class ValidationError(ServiceError):
    """Raised when input validation fails"""
    pass

class ProcessingError(ServiceError):
    """Raised when processing fails"""
    pass
