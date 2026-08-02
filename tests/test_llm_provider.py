from llm_provider import OpenAICompatibleProvider
from unittest.mock import patch, MagicMock

@patch("llm_provider.OpenAI")
def test_openai_provider(mock_openai):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices[0].message.content = '{"action":"click"}'
    mock_openai.return_value = mock_client
    
    provider = OpenAICompatibleProvider(api_key="test", base_url="http://test.local", model_name="test-model")
    res = provider.analyze_screen(b"fake_image_bytes", "system prompt", "user prompt")
    
    assert '{"action":"click"}' in res
    mock_client.chat.completions.create.assert_called_once()
