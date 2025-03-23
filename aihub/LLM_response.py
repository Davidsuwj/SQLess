import requests
import json
import uuid  # 用於生成唯一的 session_id 字串
import settings

session_store = {}

def session_id(API_KEY):
    """建立 API 連線 Session，並返回一個字串型的 session_id"""
    session = requests.Session()
    session.headers.update({
        "api-key": API_KEY,
        "Content-Type": "application/json"
    })
    
    new_session_id = str(uuid.uuid4())  # 產生唯一的 session_id
    # 同時儲存 session 與對話歷史 (history)
    session_store[new_session_id] = {
        "session": session,
        "history": [] 
    }
    return new_session_id  

def chat_response(API_KEY, session_id,service, version,func, question):
    """使用 session_id 發送請求，同時傳送完整的對話歷史"""
    endpoint = settings.endpoint
    api_version = settings.api_version
    

    session_obj = session_store.get(session_id)
    
    if session_obj is None:
        return "Invalid session_id"
    
    session = session_obj["session"]
    history = session_obj["history"]
    
  
    history.append({"role": "user", "content": question})
    
  
    response = session.post(
        f"{endpoint}/openai/deployments/{version}/chat/completions?api-version={api_version}",
        json={
            "messages": history,
            "max_tokens": 4096,
            "temperature": 0.2,
            "n": 1
        }
    )
    
  
    if response.status_code != 200:
        return f"API Error: {response.status_code} - {response.text}"
    
    result = response.json()
    answer = result.get('choices', [{}])[0].get('message', {}).get('content', 'Error: No response').strip()
    
 
    history.append({"role": "assistant", "content": answer})
    
    return answer

