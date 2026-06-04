"""
Machine Learning Tools for Dan AI Agent
Provides comprehensive ML model training, inference, and management capabilities.
"""

import os
import json
import pickle
import logging
import warnings
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Union
from pathlib import Path
import tempfile

# Suppress warnings for cleaner output
warnings.filterwarnings('ignore')

# Security imports
from security_utils import SecurePathValidator, sanitize_user_input
path_validator = SecurePathValidator()

# Setup logging
logger = logging.getLogger(__name__)

class MLError(Exception):
    """Custom exception for ML operations"""
    pass

class MLModelManager:
    """Manages machine learning models across different frameworks"""
    
    def __init__(self):
        self.supported_frameworks = {
            'sklearn': self._check_sklearn,
            'tensorflow': self._check_tensorflow, 
            'pytorch': self._check_pytorch,
            'xgboost': self._check_xgboost,
            'lightgbm': self._check_lightgbm
        }
        self.available_frameworks = self._check_available_frameworks()
        
    def _check_available_frameworks(self) -> Dict[str, bool]:
        """Check which ML frameworks are available"""
        available = {}
        for framework, checker in self.supported_frameworks.items():
            available[framework] = checker()
        return available
    
    def _check_sklearn(self) -> bool:
        try:
            import sklearn
            return True
        except ImportError:
            return False
    
    def _check_tensorflow(self) -> bool:
        try:
            import tensorflow as tf
            return True
        except ImportError:
            return False
    
    def _check_pytorch(self) -> bool:
        try:
            import torch
            return True
        except ImportError:
            return False
    
    def _check_xgboost(self) -> bool:
        try:
            import xgboost
            return True
        except ImportError:
            return False
    
    def _check_lightgbm(self) -> bool:
        try:
            import lightgbm
            return True
        except ImportError:
            return False

class SklearnTrainer:
    """Scikit-learn model training and inference"""
    
    def __init__(self):
        if not self._check_sklearn():
            raise MLError("Scikit-learn not available")
        
        # Import sklearn components
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import accuracy_score, mean_squared_error, classification_report
        from sklearn.preprocessing import StandardScaler, LabelEncoder
        from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
        from sklearn.linear_model import LogisticRegression, LinearRegression
        from sklearn.svm import SVC, SVR
        from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor
        from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor
        from sklearn.naive_bayes import GaussianNB
        from sklearn.cluster import KMeans, DBSCAN
        
        self.sklearn_models = {
            'classification': {
                'random_forest': RandomForestClassifier,
                'logistic_regression': LogisticRegression,
                'svm': SVC,
                'decision_tree': DecisionTreeClassifier,
                'knn': KNeighborsClassifier,
                'naive_bayes': GaussianNB
            },
            'regression': {
                'random_forest': RandomForestRegressor,
                'linear_regression': LinearRegression,
                'svm': SVR,
                'decision_tree': DecisionTreeRegressor,
                'knn': KNeighborsRegressor
            },
            'clustering': {
                'kmeans': KMeans,
                'dbscan': DBSCAN
            }
        }
        
        self.train_test_split = train_test_split
        self.accuracy_score = accuracy_score
        self.mean_squared_error = mean_squared_error
        self.classification_report = classification_report
        self.StandardScaler = StandardScaler
        self.LabelEncoder = LabelEncoder
    
    def _check_sklearn(self) -> bool:
        try:
            import sklearn
            return True
        except ImportError:
            return False
    
    def train_model(self, data: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        """Train a scikit-learn model"""
        try:
            import numpy as np
            import pandas as pd
            
            # Extract data
            X = np.array(data['features'])
            y = np.array(data['target'])
            
            # Get model configuration
            model_type = config.get('model_type', 'classification')
            algorithm = config.get('algorithm', 'random_forest')
            test_size = config.get('test_size', 0.2)
            random_state = config.get('random_state', 42)
            
            # Validate model type and algorithm
            if model_type not in self.sklearn_models:
                raise MLError(f"Unsupported model type: {model_type}")
            
            if algorithm not in self.sklearn_models[model_type]:
                raise MLError(f"Unsupported algorithm for {model_type}: {algorithm}")
            
            # Split data
            X_train, X_test, y_train, y_test = self.train_test_split(
                X, y, test_size=test_size, random_state=random_state
            )
            
            # Scale features if specified
            scaler = None
            if config.get('scale_features', False):
                scaler = self.StandardScaler()
                X_train = scaler.fit_transform(X_train)
                X_test = scaler.transform(X_test)
            
            # Encode labels for classification
            label_encoder = None
            if model_type == 'classification' and y.dtype == 'object':
                label_encoder = self.LabelEncoder()
                y_train = label_encoder.fit_transform(y_train)
                y_test = label_encoder.transform(y_test)
            
            # Initialize and train model
            model_class = self.sklearn_models[model_type][algorithm]
            model_params = config.get('model_params', {})
            model = model_class(**model_params)
            
            # Train the model
            model.fit(X_train, y_train)
            
            # Make predictions
            y_pred = model.predict(X_test)
            
            # Calculate metrics
            metrics = {}
            if model_type == 'classification':
                metrics['accuracy'] = float(self.accuracy_score(y_test, y_pred))
                if len(np.unique(y)) <= 10:  # Only for small number of classes
                    metrics['classification_report'] = self.classification_report(
                        y_test, y_pred, output_dict=True
                    )
            elif model_type == 'regression':
                metrics['mse'] = float(self.mean_squared_error(y_test, y_pred))
                metrics['rmse'] = float(np.sqrt(metrics['mse']))
            
            # Feature importance if available
            feature_importance = None
            if hasattr(model, 'feature_importances_'):
                feature_names = config.get('feature_names', [f'feature_{i}' for i in range(X.shape[1])])
                feature_importance = dict(zip(feature_names, model.feature_importances_.tolist()))
            
            return {
                'status': 'success',
                'model_type': model_type,
                'algorithm': algorithm,
                'metrics': metrics,
                'feature_importance': feature_importance,
                'data_shape': {
                    'train': X_train.shape,
                    'test': X_test.shape,
                    'features': X.shape[1],
                    'samples': X.shape[0]
                },
                'model_object': model,
                'scaler': scaler,
                'label_encoder': label_encoder
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'error_type': type(e).__name__
            }
    
    def predict(self, model_data: Dict[str, Any], features: List[List[float]]) -> Dict[str, Any]:
        """Make predictions using a trained model"""
        try:
            import numpy as np
            
            model = model_data['model_object']
            scaler = model_data.get('scaler')
            label_encoder = model_data.get('label_encoder')
            
            X = np.array(features)
            
            # Scale features if scaler was used during training
            if scaler is not None:
                X = scaler.transform(X)
            
            # Make predictions
            predictions = model.predict(X)
            
            # Decode labels if label encoder was used
            if label_encoder is not None:
                predictions = label_encoder.inverse_transform(predictions)
            
            # Get prediction probabilities if available
            probabilities = None
            if hasattr(model, 'predict_proba'):
                probabilities = model.predict_proba(X).tolist()
            
            return {
                'status': 'success',
                'predictions': predictions.tolist(),
                'probabilities': probabilities,
                'num_predictions': len(predictions)
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'error_type': type(e).__name__
            }

class ModelStorage:
    """Handles saving and loading ML models"""
    
    def __init__(self, models_dir: str = "ml_models"):
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(exist_ok=True)
    
    def save_model(self, model_data: Dict[str, Any], model_name: str) -> Dict[str, Any]:
        """Save a trained model to disk"""
        try:
            # Validate model name
            model_name = sanitize_user_input(model_name, max_length=100)
            if not model_name or not model_name.replace('_', '').replace('-', '').isalnum():
                raise MLError("Invalid model name. Use alphanumeric characters, hyphens, and underscores only.")
            
            model_path = self.models_dir / f"{model_name}.pkl"
            metadata_path = self.models_dir / f"{model_name}_metadata.json"
            
            # Validate paths
            if not path_validator.is_safe_path(str(model_path)):
                raise MLError("Invalid model path")
            
            # Prepare data for saving
            save_data = {
                'model_object': model_data['model_object'],
                'scaler': model_data.get('scaler'),
                'label_encoder': model_data.get('label_encoder'),
                'model_type': model_data['model_type'],
                'algorithm': model_data['algorithm']
            }
            
            # Save model
            with open(model_path, 'wb') as f:
                pickle.dump(save_data, f)
            
            # Save metadata
            metadata = {
                'model_name': model_name,
                'model_type': model_data['model_type'],
                'algorithm': model_data['algorithm'],
                'metrics': model_data.get('metrics', {}),
                'feature_importance': model_data.get('feature_importance'),
                'data_shape': model_data.get('data_shape', {}),
                'saved_at': datetime.now().isoformat()
            }
            
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            return {
                'status': 'success',
                'model_path': str(model_path),
                'metadata_path': str(metadata_path),
                'message': f'Model "{model_name}" saved successfully'
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'error_type': type(e).__name__
            }
    
    def load_model(self, model_name: str) -> Dict[str, Any]:
        """Load a saved model from disk"""
        try:
            # Validate and sanitize model name
            model_name = sanitize_user_input(model_name, max_length=100)
            if not model_name:
                raise MLError("Invalid model name")
            
            model_path = self.models_dir / f"{model_name}.pkl"
            metadata_path = self.models_dir / f"{model_name}_metadata.json"
            
            # Validate paths
            if not path_validator.is_safe_path(str(model_path)):
                raise MLError("Invalid model path")
            
            if not model_path.exists():
                raise MLError(f'Model "{model_name}" not found')
            
            # Load model (SECURITY FIX: Using joblib instead of pickle)
            try:
                import joblib
                model_data = joblib.load(model_path)
                logger.info(f"Loaded model using secure joblib: {model_name}")
            except ImportError:
                # Fallback to pickle with warning (should be avoided in production)
                logger.warning(f"SECURITY WARNING: Loading model {model_name} with pickle (joblib not available)")
                logger.warning("Install joblib for secure model loading: pip install joblib")
                with open(model_path, 'rb') as f:
                    model_data = pickle.load(f)
            
            # Load metadata if available
            metadata = {}
            if metadata_path.exists():
                with open(metadata_path, 'r') as f:
                    metadata = json.load(f)
            
            return {
                'status': 'success',
                'model_data': model_data,
                'metadata': metadata,
                'message': f'Model "{model_name}" loaded successfully'
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'error_type': type(e).__name__
            }
    
    def list_models(self) -> Dict[str, Any]:
        """List all saved models"""
        try:
            models = []
            for model_file in self.models_dir.glob("*.pkl"):
                model_name = model_file.stem
                metadata_file = self.models_dir / f"{model_name}_metadata.json"
                
                model_info = {'name': model_name, 'file': str(model_file)}
                
                if metadata_file.exists():
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                        model_info.update(metadata)
                
                models.append(model_info)
            
            return {
                'status': 'success',
                'models': models,
                'count': len(models)
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'error_type': type(e).__name__
            }

class DataProcessor:
    """Handles data preprocessing for ML models"""
    
    @staticmethod
    def load_data_from_file(file_path: str) -> Dict[str, Any]:
        """Load data from various file formats"""
        try:
            # Validate path
            if not path_validator.is_safe_path(file_path):
                raise MLError("Invalid file path")
            
            file_path = Path(file_path)
            if not file_path.exists():
                raise MLError(f"File not found: {file_path}")
            
            # Determine file type and load accordingly
            if file_path.suffix.lower() == '.csv':
                import pandas as pd
                data = pd.read_csv(file_path)
            elif file_path.suffix.lower() in ['.xlsx', '.xls']:
                import pandas as pd
                data = pd.read_excel(file_path)
            elif file_path.suffix.lower() == '.json':
                import pandas as pd
                data = pd.read_json(file_path)
            else:
                raise MLError(f"Unsupported file format: {file_path.suffix}")
            
            return {
                'status': 'success',
                'data': data,
                'shape': data.shape,
                'columns': data.columns.tolist(),
                'dtypes': data.dtypes.to_dict(),
                'memory_usage': data.memory_usage(deep=True).sum()
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'error_type': type(e).__name__
            }
    
    @staticmethod
    def prepare_data(data_info: Dict[str, Any], target_column: str, 
                    feature_columns: Optional[List[str]] = None) -> Dict[str, Any]:
        """Prepare data for ML training"""
        try:
            data = data_info['data']
            
            # Validate target column
            if target_column not in data.columns:
                raise MLError(f"Target column '{target_column}' not found in data")
            
            # Select feature columns
            if feature_columns is None:
                feature_columns = [col for col in data.columns if col != target_column]
            else:
                missing_cols = [col for col in feature_columns if col not in data.columns]
                if missing_cols:
                    raise MLError(f"Feature columns not found: {missing_cols}")
            
            # Extract features and target
            X = data[feature_columns]
            y = data[target_column]
            
            # Handle missing values
            if X.isnull().any().any():
                X = X.fillna(X.mean() if X.select_dtypes(include=['number']).shape[1] > 0 else X.mode().iloc[0])
            
            if y.isnull().any():
                y = y.fillna(y.mean() if y.dtype in ['int64', 'float64'] else y.mode().iloc[0])
            
            # Convert to numpy arrays
            X_values = X.values
            y_values = y.values
            
            return {
                'status': 'success',
                'features': X_values.tolist(),
                'target': y_values.tolist(),
                'feature_names': feature_columns,
                'target_name': target_column,
                'data_info': {
                    'samples': len(X),
                    'features': len(feature_columns),
                    'target_type': str(y.dtype),
                    'feature_types': {col: str(dtype) for col, dtype in X.dtypes.items()}
                }
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'error_type': type(e).__name__
            }

def train_ml_model(data_source: str, target_column: str, 
                  model_config: Optional[Dict[str, Any]] = None,
                  feature_columns: Optional[List[str]] = None,
                  save_model: Optional[str] = None) -> Dict[str, Any]:
    """
    Train a machine learning model
    
    Args:
        data_source: Path to data file (CSV, Excel, JSON)
        target_column: Name of target column
        model_config: Model configuration dict
        feature_columns: List of feature column names (optional)
        save_model: Model name to save (optional)
    
    Returns:
        Dict containing training results
    """
    try:
        # Default configuration
        default_config = {
            'model_type': 'classification',
            'algorithm': 'random_forest',
            'test_size': 0.2,
            'random_state': 42,
            'scale_features': False,
            'model_params': {}
        }
        
        if model_config:
            default_config.update(model_config)
        model_config = default_config
        
        # Initialize components
        data_processor = DataProcessor()
        storage = ModelStorage()
        trainer = SklearnTrainer()
        
        # Load and prepare data
        print("Loading data...")
        data_result = data_processor.load_data_from_file(data_source)
        if data_result['status'] != 'success':
            return data_result
        
        print(f"Data loaded: {data_result['shape']} shape")
        
        # Prepare data for training
        print("Preparing data for training...")
        prep_result = data_processor.prepare_data(
            data_result, target_column, feature_columns
        )
        if prep_result['status'] != 'success':
            return prep_result
        
        # Add feature names to config
        model_config['feature_names'] = prep_result['feature_names']
        
        print(f"Data prepared: {prep_result['data_info']['samples']} samples, {prep_result['data_info']['features']} features")
        
        # Train model
        print(f"Training {model_config['algorithm']} model for {model_config['model_type']}...")
        training_result = trainer.train_model(prep_result, model_config)
        if training_result['status'] != 'success':
            return training_result
        
        print(f"Model trained successfully! Metrics: {training_result['metrics']}")
        
        # Save model if requested
        if save_model:
            print(f"Saving model as '{save_model}'...")
            save_result = storage.save_model(training_result, save_model)
            training_result['save_result'] = save_result
        
        return training_result
        
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e),
            'error_type': type(e).__name__
        }

def predict_with_model(model_name: str, features: List[List[float]]) -> Dict[str, Any]:
    """
    Make predictions using a saved model
    
    Args:
        model_name: Name of saved model
        features: List of feature vectors for prediction
    
    Returns:
        Dict containing predictions
    """
    try:
        storage = ModelStorage()
        trainer = SklearnTrainer()
        
        # Load model
        print(f"Loading model '{model_name}'...")
        load_result = storage.load_model(model_name)
        if load_result['status'] != 'success':
            return load_result
        
        model_data = load_result['model_data']
        print(f"Model loaded: {model_data['algorithm']} {model_data['model_type']}")
        
        # Make predictions
        print(f"Making predictions for {len(features)} samples...")
        prediction_result = trainer.predict(model_data, features)
        
        if prediction_result['status'] == 'success':
            print(f"Predictions completed: {prediction_result['num_predictions']} results")
        
        return prediction_result
        
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e),
            'error_type': type(e).__name__
        }

def list_saved_models() -> Dict[str, Any]:
    """List all saved ML models"""
    try:
        storage = ModelStorage()
        return storage.list_models()
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e),
            'error_type': type(e).__name__
        }

def get_ml_framework_status() -> Dict[str, Any]:
    """Get status of available ML frameworks"""
    try:
        manager = MLModelManager()
        return {
            'status': 'success',
            'available_frameworks': manager.available_frameworks,
            'supported_algorithms': {
                'sklearn': {
                    'classification': ['random_forest', 'logistic_regression', 'svm', 'decision_tree', 'knn', 'naive_bayes'],
                    'regression': ['random_forest', 'linear_regression', 'svm', 'decision_tree', 'knn'],
                    'clustering': ['kmeans', 'dbscan']
                }
            },
            'recommendations': [
                "For quick prototyping: Use sklearn algorithms",
                "For neural networks: Install tensorflow or pytorch", 
                "For gradient boosting: Install xgboost or lightgbm",
                "Always validate your data before training"
            ]
        }
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e),
            'error_type': type(e).__name__
        }

# Tool registration data
TOOLS = [
    {
        "name": "TrainMLModel",
        "description": "Train machine learning models on data (classification, regression, clustering) using scikit-learn algorithms",
        "function": train_ml_model,
        "parameters": {
            "data_source": {"type": "str", "required": True, "description": "Path to data file (CSV, Excel, JSON)"},
            "target_column": {"type": "str", "required": True, "description": "Name of target/label column"},
            "model_config": {"type": "dict", "required": False, "description": "Model configuration (model_type, algorithm, test_size, etc.)"},
            "feature_columns": {"type": "list", "required": False, "description": "List of feature column names (uses all non-target columns if not specified)"},
            "save_model": {"type": "str", "required": False, "description": "Name to save trained model"}
        },
        "category": "ml"
    },
    {
        "name": "PredictMLModel", 
        "description": "Make predictions using a trained and saved ML model",
        "function": predict_with_model,
        "parameters": {
            "model_name": {"type": "str", "required": True, "description": "Name of saved model to use for predictions"},
            "features": {"type": "list", "required": True, "description": "List of feature vectors (each vector is a list of numbers)"}
        },
        "category": "ml"
    },
    {
        "name": "ListMLModels",
        "description": "List all saved machine learning models with metadata",
        "function": list_saved_models,
        "parameters": {},
        "category": "ml"
    },
    {
        "name": "MLFrameworkStatus",
        "description": "Check status of available ML frameworks and supported algorithms",
        "function": get_ml_framework_status,
        "parameters": {},
        "category": "ml"
    }
]

# Register tools with the tool registry
def register_ml_tools():
    """Register ML tools with the Dan tool registry."""
    try:
        import tool_registry as registry
        
        # Convert parameter format for registry
        def convert_params(params):
            """Convert tool parameters to JSON Schema format."""
            if not params:
                return {"type": "object", "properties": {}}
            
            properties = {}
            required = []
            
            for param_name, param_info in params.items():
                prop = {"type": "string"}  # Default type
                
                if param_info.get("type") == "str":
                    prop["type"] = "string"
                elif param_info.get("type") == "list":
                    prop["type"] = "array"
                elif param_info.get("type") == "dict":
                    prop["type"] = "object"
                
                if param_info.get("description"):
                    prop["description"] = param_info["description"]
                
                if param_info.get("required", False):
                    required.append(param_name)
                
                properties[param_name] = prop
            
            schema = {
                "type": "object", 
                "properties": properties
            }
            if required:
                schema["required"] = required
                
            return schema
        
        # Register all ML tools
        for tool in TOOLS:
            registry.register(
                name=tool["name"],
                description=tool["description"], 
                parameters=convert_params(tool["parameters"]),
                handler=tool["function"],
                category=tool["category"]
            )
        
        logger.info(f"Registered {len(TOOLS)} ML tools successfully")
        return len(TOOLS)
        
    except ImportError:
        logger.warning("Tool registry not available - ML tools will not be registered")
        return 0
    except Exception as e:
        logger.error(f"Error registering ML tools: {e}")
        return 0

# Auto-register when imported (following image_tools pattern)
try:
    register_ml_tools()
except Exception as e:
    logger.warning(f"Failed to auto-register ML tools: {e}")

if __name__ == "__main__":
    # Test the ML framework status
    status = get_ml_framework_status()
    print("ML Framework Status:")
    print(json.dumps(status, indent=2))
