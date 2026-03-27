"""
Tools 模块测试
"""

import pytest
import sys
sys.path.insert(0, '..')


class TestExternalInfoTool:
    """外部信息工具测试"""
    
    def test_tool_创建(self):
        """工具能正常创建"""
        from tools import GetExternalInfoTool
        
        tool = GetExternalInfoTool()
        assert tool.name == "get_external_info"
        assert tool.description != ""
    
    def test_tool_注册平台(self):
        """平台注册功能"""
        from tools import GetExternalInfoTool, PlatformAdapter
        
        class MockAdapter(PlatformAdapter):
            def get_name(self) -> str:
                return "mock"
            
            def query_order(self, order_id: str, **kwargs):
                from tools.external_info import ExternalInfoResponse
                return ExternalInfoResponse(success=True, data={"id": order_id}, platform="mock")
            
            def query_logistics(self, logistics_id: str, **kwargs):
                from tools.external_info import ExternalInfoResponse
                return ExternalInfoResponse(success=True, data={"id": logistics_id}, platform="mock")
            
            def query_refund(self, refund_id: str, **kwargs):
                from tools.external_info import ExternalInfoResponse
                return ExternalInfoResponse(success=True, data={"id": refund_id}, platform="mock")
            
            def query_user(self, user_id: str, **kwargs):
                from tools.external_info import ExternalInfoResponse
                return ExternalInfoResponse(success=True, data={"id": user_id}, platform="mock")
            
            def transfer_to_human(self, session_id: str, reason: str, **kwargs):
                from tools.external_info import ExternalInfoResponse
                return ExternalInfoResponse(success=True, message="已转人工", platform="mock")
        
        tool = GetExternalInfoTool()
        adapter = MockAdapter()
        tool.register_platform(adapter)
        
        assert "mock" in tool.list_platforms()
    
    def test_tool_查询订单(self):
        """查询订单功能"""
        from tools import GetExternalInfoTool, PlatformAdapter
        
        class MockAdapter(PlatformAdapter):
            def get_name(self) -> str:
                return "test"
            
            def query_order(self, order_id: str, **kwargs):
                from tools.external_info import ExternalInfoResponse
                return ExternalInfoResponse(
                    success=True,
                    data={"order_id": order_id, "status": "已完成"},
                    platform="test"
                )
            
            def query_logistics(self, logistics_id: str, **kwargs):
                from tools.external_info import ExternalInfoResponse
                return ExternalInfoResponse(success=True, data={}, platform="test")
            
            def query_refund(self, refund_id: str, **kwargs):
                from tools.external_info import ExternalInfoResponse
                return ExternalInfoResponse(success=True, data={}, platform="test")
            
            def query_user(self, user_id: str, **kwargs):
                from tools.external_info import ExternalInfoResponse
                return ExternalInfoResponse(success=True, data={}, platform="test")
            
            def transfer_to_human(self, session_id: str, reason: str, **kwargs):
                from tools.external_info import ExternalInfoResponse
                return ExternalInfoResponse(success=True, message="已转人工", platform="test")
        
        tool = GetExternalInfoTool()
        tool.register_platform(MockAdapter())
        
        result = tool.execute(
            info_type="order",
            params={"order_id": "12345"}
        )
        
        assert result.success is True
        assert result.data["order_id"] == "12345"
    
    def test_tool_未知类型(self):
        """未知信息类型返回错误"""
        from tools import GetExternalInfoTool
        
        tool = GetExternalInfoTool()
        
        result = tool.execute(
            info_type="unknown_type",
            params={}
        )
        
        assert result.success is False
        assert "未知的信息类型" in result.error
    
    def test_tool_无平台(self):
        """没有注册平台时返回错误"""
        from tools import GetExternalInfoTool
        
        tool = GetExternalInfoTool()
        
        result = tool.execute(
            info_type="order",
            params={"order_id": "12345"}
        )
        
        assert result.success is False
        assert "没有可用的平台" in result.error


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
