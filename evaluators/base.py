from abc import ABC, abstractmethod
from typing import Dict, Any


class AbstractEvaluator(ABC):
    @abstractmethod
    def evaluate(self) -> Dict[str, Any]:
        pass
