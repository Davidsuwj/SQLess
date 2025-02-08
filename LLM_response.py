import json
from langchain.memory import ConversationBufferMemory
from langchain.schema import messages_to_dict
import uuid
import os
from openai import OpenAI
import settings

def convert_message_format(message):
    """將各種格式的訊息統一轉換為 {'role': ..., 'content': ...} 格式"""
    if "role" in message and "content" in message:
        return message

    msg_type = message.get("type")
    if msg_type == "human":
        role = "user"
    elif msg_type == "ai":
        role = "assistant"
    else:
        role = "user"
    content = message.get("data", {}).get("content", "")
    return {"role": role, "content": content}


def chat(API_KEY,BASE_URL,MODEL,memory,prompt):

    
    existing_messages = messages_to_dict(memory.chat_memory.messages)
    converted_messages = [convert_message_format(msg) for msg in existing_messages]
   
    prompt_message = {"role": "user", "content": prompt}
    messages = converted_messages + [prompt_message]

        
    try:
        client = OpenAI(api_key=API_KEY,base_url=BASE_URL)

        completion = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        stream=False
        )
        response = completion.choices[0].message.content
    except Exception as e:
        print("認證錯誤:", e)
        return "認證失敗，請檢查 API_KEY 與相關設定。"
    except Exception as e:
        print("其他錯誤:", e)
        return "發生其他錯誤。"
    
    

    memory.chat_memory.add_user_message(prompt)
    memory.chat_memory.add_ai_message(response)

    return response

# if __name__ == "__main__":
#     memory = ConversationBufferMemory(return_messages=True)

#     while True:
#         prompt = input('enter: ')
#         for model in settings.MODELS: 
#             result = chat(settings.API_KEY,settings.BASE_URL,model,memory,prompt)
#             if '認證失敗' not in result:
#                 print(result)
#                 break


