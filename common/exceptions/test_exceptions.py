"""
Test Exceptions - 测试执行自定义异常
"""


class TestException(Exception):
    """测试异常基类"""
    pass


class TestPreconditionError(TestException):
    """测试前置条件不满足"""
    pass


class TestTimeoutError(TestException):
    """测试超时"""
    pass


class TestDataError(TestException):
    """测试数据异常"""
    pass


class TestEnvironmentError(TestException):
    """测试环境异常"""
    pass