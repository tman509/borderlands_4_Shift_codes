"""
Unit tests for scheduler functionality.
"""

import pytest
import time
import threading
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, pat