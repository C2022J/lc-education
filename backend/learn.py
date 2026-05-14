import os
from langchain_deepseek import ChatDeepSeek
from langchain_core.messages import SystemMessage, HumanMessage
from dotenv import load_dotenv
from langchain.agents import create_agent

load_dotenv()
api_key = os.getenv("DEEPSEEK_API_KEY")
model = ChatDeepSeek(model="deepseek-chat", api_key=api_key)

agent = create_agent(model=model)
result = agent.invoke({"messages": [SystemMessage(content="You are a helpful assistant."), HumanMessage(content="What is the capital of France?")]})

# result = agent.invoke({"messages":[SystemMessage(content="You are a helpful assistant."), HumanMessage(content="What is the capital of France?")]})

print(type(result))
print(result)
for message in result["messages"]:
    message.pretty_print()
for key, value in result.items():
    print(f"{key}:{value}")