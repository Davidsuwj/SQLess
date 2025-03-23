/**
 * SQLess 聊天界面 JavaScript
 * 主要功能包括：
 * 1. 聊天界面管理 (消息發送、接收和顯示)
 * 2. 思考鏈(Chain of Thought)視覺化展示
 * 3. SQL 查詢結果與圖表展示
 * 4. 資料表選擇下拉選單
 */

//======================================================
// 初始化設置
//======================================================

// 聊天相關元素
const chatBox = document.getElementById('chatBox');
const userInput = document.getElementById('userInput');
const sendButton = document.getElementById('sendButton');

// 表格選擇下拉選單相關元素
const filterDropdown = document.getElementById('filterDropdown');
const dropdownHeader = document.getElementById('dropdownHeader');
const dropdownBody = document.getElementById('dropdownBody');
const dropdownSearch = document.getElementById('dropdownSearch');
const dropdownList = document.getElementById('dropdownList');
const dropdownSelected = document.getElementById('dropdownSelected');

// 其他UI元素
const chartToggle = document.querySelector('.chart-toggle');
const chartPanel = document.querySelector('.chart-panel');
const mainContent = document.querySelector('.main-content');
const container = document.querySelector('.container');

/**
 * 根據是否已選擇資料表更新輸入框狀態
 */
function updateUserInputStatus() {
  if (dropdownSelected.textContent.trim() === "Choose Table") {
    userInput.disabled = true;
    userInput.placeholder = "請先選擇資料表";
  } else {
    userInput.disabled = false;
    userInput.placeholder = "傳訊息給SQLess";
  }
}

// 初始化頁面設置
updateUserInputStatus();

//======================================================
// 啟動畫面與初始動畫
//======================================================

/**
 * 啟動畫面淡出，顯示主界面
 */
window.addEventListener('load', () => {
  setTimeout(() => {
    const splashScreen = document.querySelector('.splash-screen');
    const container = document.querySelector('.container');
    const header = document.querySelector('.header');
    
    // 淡出啟動畫面，顯示主界面
    splashScreen.style.opacity = '0';
    container.classList.add('visible');
    header.classList.add('visible');
    setTimeout(() => {
      splashScreen.style.display = 'none';
    }, 500);
    document.body.style.background = 'rgba(41, 41, 41,1)';
  }, 3000); // 3秒後開始淡出
});

//======================================================
// 文字輸入框自適應高度功能
//======================================================

/**
 * 根據內容自動調整輸入框高度
 */
function updateTextareaHeight() {
  const lineHeight = parseFloat(getComputedStyle(userInput).lineHeight);
  const maxHeight = lineHeight * 16; // 最多允許16行文字
  
  // 先重置高度以便正確計算新高度
  userInput.style.height = 'auto';
  
  // 設置新高度並限制最大高度
  const newHeight = Math.min(userInput.scrollHeight, maxHeight);
  userInput.style.height = newHeight + 'px';
  
  // 當高度超過最大值時啟用垂直滾動條
  userInput.style.overflowY = userInput.scrollHeight > maxHeight ? 'auto' : 'hidden';
}

// 當用戶輸入時調整高度並控制發送按鈕顯示
userInput.addEventListener('input', () => {
  updateTextareaHeight();
  // 當輸入框有內容時顯示發送按鈕
  sendButton.classList.toggle('visible', userInput.value.trim() !== '');
});

//======================================================
// SSE (Server-Sent Events) 連接 - 用於思考鏈功能
//======================================================

/**
 * 建立與後端的SSE連接，用於接收AI思考過程的實時輸出
 */
const sse = new EventSource('/stream_node_outputs');
sse.onmessage = function(e) {
  console.log("[SSE] Received:", e.data);
  // 接收到AI的思考過程，追加到思考鏈顯示
  appendChainOfThought('bot', e.data);
};

//======================================================
// 消息發送與接收相關功能
//======================================================

// 儲存AI開始思考的時間(用於計算思考時間)
var typingStartTime = null;

/**
 * 發送用戶訊息到後端API並處理回應
 */
async function sendMessage() {
  // 確認用戶已選擇資料表
  if (dropdownSelected.textContent.trim() === "Choose Table") {
    alert("請先選擇資料表");
    return;
  }
  
  const message = userInput.value.trim();
  if (!message) return;

  // 清空圖表區域並顯示加載動畫
  hideCharts();
  showChartsLoading();

  // 顯示用戶發送的訊息
  appendMessage('user', message);
  
  // 重置輸入框
  userInput.value = '';
  userInput.style.height = 'auto';
  sendButton.classList.remove('visible');
  
  // 顯示AI正在思考的狀態
  setTypingStatus(true);

  try {
    // 發送訊息到後端API
    const response = await fetch('/api/message', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message })
    });
    const data = await response.json();

    // 結束思考狀態
    setTypingStatus(false);

    // 顯示AI回應
    if (data.response) {
      appendMessage('bot', data.response, data.sql, data.chat_index, data.status);
    } else {
      appendMessage('bot', 'Error: token數已達上限，請重新整理頁面');
    }
  } catch (error) {
    setTypingStatus(false);
    console.error('Error:', error);
    appendMessage('bot', 'Error: token數已達上限，請重新整理頁面');
  } finally {
    // 無論成功或失敗，都嘗試載入圖表
    await loadCharts();
  }
}

// 綁定發送訊息功能到按鈕和Enter鍵
sendButton.addEventListener('click', sendMessage);
userInput.addEventListener('keypress', async (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    await sendMessage();
  }
});

/**
 * 設置AI思考狀態的顯示與隱藏
 * @param {boolean} isTyping - 是否正在思考中
 */
function setTypingStatus(isTyping) {
  // 獲取現有的狀態指示器
  const existingIndicator = document.querySelector('.status-indicator.typing');

  // 獲取最新的思考鏈摘要元素
  const summaryIndicators = chatBox.querySelectorAll('summary');
  const summaryIndicator = summaryIndicators[summaryIndicators.length - 1];

  // 獲取最新的思考鏈詳情元素
  const detailElems = document.querySelectorAll('details.chain-of-thought');
  const detailElem = detailElems[detailElems.length - 1];

  // 如果已有狀態指示器，移除它並更新思考鏈摘要
  if (existingIndicator) {
    existingIndicator.remove();
    
    if (summaryIndicator) {
      if (typingStartTime !== null) {
        const elapsedSeconds = Math.round((new Date() - typingStartTime) / 1000);
        summaryIndicator.textContent = "推理花了 " + elapsedSeconds + " 秒";
        typingStartTime = null; 
      } else {
        summaryIndicator.textContent = "推理完成";
      }
      summaryIndicator.classList.remove('typing');
    }
    
    if (detailElem) {
      detailElem.open = false;
    }
  }

  // 如果正在思考中，創建並顯示思考指示器
  if (isTyping) {
    typingStartTime = new Date();
    
    const typingIndicator = document.createElement('div');
    typingIndicator.className = 'chat-message bot bubble status-indicator typing';
    
    // 創建水平水波紋特效文字
    const text = '推理中請稍後';
    for (let i = 0; i < 1; i++) {
      const span = document.createElement('span');
      span.className = 'wave-text';
      span.textContent = text;
      span.style.animationDelay = (i * 0.1) + 's';
      typingIndicator.appendChild(span);
    }
    
    chatBox.appendChild(typingIndicator);
    chatBox.scrollTop = chatBox.scrollHeight;
  }
}

/**
 * 格式化當前時間為 HH:MM 格式
 * @returns {string} 格式化後的時間字符串
 */
function formatTime() {
  const now = new Date();
  return now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

//======================================================
// 思考鏈(Chain of Thought)相關功能
//======================================================

/**
 * 追加AI思考過程到思考鏈顯示
 * @param {string} sender - 訊息發送者('user'或'bot')
 * @param {string} text - 思考內容文本
 */
function appendChainOfThought(sender, text) {
  if (typeof chatBox === 'undefined') {
    console.error("chatBox 未定義！");
    return;
  }
  
  // 檢查是否需要創建新的思考鏈或追加到現有思考鏈
  const chainMsgs = chatBox.querySelectorAll('.chain-of-thought-message');
  const existingChainMsg = chainMsgs.length > 0 ? chainMsgs[chainMsgs.length - 1] : null;
  console.log("text:", text.substr(0,2));
  
  // 如果不是以"首先"開頭，則追加到現有思考鏈
  if (text.substr(0,2) != "首先") {
    console.log("existingChainMsg:", existingChainMsg);
    if (existingChainMsg) {
      // 找到最新的思考鏈內容區塊並追加新內容
      const contentDiv = existingChainMsg.querySelector('.chain-content');
      if (sender === 'bot' && typingStartTime != null) {
        // 如果內容包含Markdown並且marked庫可用，使用marked解析
        if (text.includes('|') && typeof marked !== 'undefined') {
          contentDiv.innerHTML += `<div style="font-size:12px; padding-top:1px; padding-left:20px; color:#aaa;">${marked.parse(text)}</div>`;
        } else {
          contentDiv.innerHTML += `<div style="font-size:12px; padding-top:1px; padding-left:20px; color:#aaa;">${text}</div>`;
        }
      } 
      // 滾動到底部
      chatBox.scrollTop = chatBox.scrollHeight;
    } else {
      // 如果還沒有思考鏈，創建新的
      createNewChainOfThought(sender, text);
    }
    return;
  }
  
  // 當文本以"首先"開頭時，創建新的思考鏈
  createNewChainOfThought(sender, text);
}

/**
 * 創建新的思考鏈顯示元素
 * @param {string} sender - 訊息發送者('user'或'bot')
 * @param {string} text - 思考內容文本
 */
function createNewChainOfThought(sender, text) {
  // 創建思考鏈消息容器
  const messageDiv = document.createElement('div');
  messageDiv.className = `chat-message chain-of-thought-message ${sender}`;
  
  // 使用<details>元素創建可折疊區域
  const detailsElem = document.createElement('details');
  detailsElem.className = 'chain-of-thought';
  detailsElem.open = true;
  
  // 創建摘要元素(默認為空，將在setTypingStatus中設置)
  const summaryElem = document.createElement('summary');
  detailsElem.appendChild(summaryElem);
  
  // 創建內容區塊
  const contentDiv = document.createElement('div');
  contentDiv.className = 'chain-content';
  
  // 根據發送者處理內容格式
  if (sender === 'bot') {
    // 如果內容包含Markdown並且marked庫可用，使用marked解析
    if (text.includes('|') && typeof marked !== 'undefined') {
      contentDiv.innerHTML = `<div style="font-size:12px; padding-top:1px; padding-left:20px; color:#aaa;">${marked.parse(text)}</div>`;
    } else {
      contentDiv.innerHTML = `<div style="font-size:12px; padding-top:1px; padding-left:20px; color:#aaa;">${text}</div>`;
    }
  } else {
    contentDiv.textContent = text;
  }
  
  // 組裝元素結構
  detailsElem.appendChild(contentDiv);
  messageDiv.appendChild(detailsElem);
  chatBox.appendChild(messageDiv);
  
  // 滾動到底部
  chatBox.scrollTop = chatBox.scrollHeight;
}

/**
 * 追加常規聊天訊息到聊天界面
 * @param {string} sender - 訊息發送者('user'或'bot')
 * @param {string} text - 訊息文本
 * @param {string} sql - SQL查詢語句(僅bot訊息有效)
 * @param {number} chat_index - 聊天索引(用於下載功能)
 * @param {string} status - 查詢狀態
 */
function appendMessage(sender, text, sql, chat_index, status) {
  if (typeof chatBox === 'undefined') {
    console.error("chatBox 未定義！");
    return;
  }
  
  // 創建訊息容器
  const messageDiv = document.createElement('div');
  messageDiv.className = `chat-message ${sender}`;

  // 添加時間信息
  const timeDiv = document.createElement('div');
  timeDiv.className = 'message-info';
  timeDiv.textContent = formatTime();

  // 創建訊息氣泡
  const bubbleDiv = document.createElement('div');
  bubbleDiv.className = 'bubble';

  // 根據發送者處理內容格式
  if (sender === 'bot') {
    console.log("text:", text);
    console.log("typeof marked:", typeof marked);
    // 如果內容包含Markdown並且marked庫可用，使用marked解析
    if (text.includes('|') && typeof marked !== 'undefined') {
      bubbleDiv.innerHTML = marked.parse(text);
    } else {
      bubbleDiv.innerHTML = text;
    }
  } else if (sender === 'user') {
    // 將用戶訊息每30字添加換行符
    const words = text.split('');
    const lines = [];
    for(let i = 0; i < words.length; i += 30) {
      lines.push(words.slice(i, i + 30).join(''));
    }
    bubbleDiv.textContent = lines.join('\n');
  }

  // 組裝基本訊息結構 
  messageDiv.appendChild(timeDiv);
  messageDiv.appendChild(bubbleDiv);

  // 如果是Bot的成功SQL查詢回應，添加SQL查看與下載功能
  if (sender === 'bot' && sql && sql.trim() !== "" && status === "success") {
    // 創建SQL操作區域容器
    const sqlActionsContainer = document.createElement('div');
    sqlActionsContainer.className = 'sql-actions-container';
    sqlActionsContainer.style.display = 'flex';
    sqlActionsContainer.style.alignItems = 'center';
    sqlActionsContainer.style.gap = '10px';

    // 創建查看SQL切換按鈕
    const sqlToggle = document.createElement('div');
    sqlToggle.className = 'toggle-sql';
    sqlToggle.innerHTML = '查看SQL ▼';
    sqlToggle.style.cursor = 'pointer';
    sqlToggle.style.fontSize = '14px';

    // 創建下載CSV按鈕
    const downloadIcon = document.createElement('div');
    downloadIcon.className = 'download-icon';
    downloadIcon.innerHTML = '<i class="btn btn-outline btn-outline-primary">download csv</i>';
    downloadIcon.style.cursor = 'pointer';
    downloadIcon.style.fontSize = '18px';
    downloadIcon.style.color = '#0078D4';
    downloadIcon.dataset.chatIndex = chat_index;

    // 下載按鈕點擊事件處理
    downloadIcon.addEventListener('click', function() {
      const index = this.dataset.chatIndex;
      console.log("下載 CSV, chat_index:", index);
      fetch(`/download_sql?chat_index=${index}`, { method: 'GET' })
        .then(response => {
          if (!response.ok) throw new Error('Network response was not ok');
          return response.blob();
        })
        .then(blob => {
          // 創建下載鏈接並觸發下載
          const url = window.URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.style.display = 'none';
          a.href = url;
          a.download = 'query_results.csv';
          document.body.appendChild(a);
          a.click();
          window.URL.revokeObjectURL(url);
        })
        .catch(error => {
          console.error('下載失敗:', error);
        });
    });

    // 組裝SQL操作區域
    sqlActionsContainer.appendChild(sqlToggle);
    sqlActionsContainer.appendChild(downloadIcon);

    // 創建SQL代碼顯示區域(默認隱藏)
    const sqlContainer = document.createElement('div');
    sqlContainer.className = 'sql-container';
    sqlContainer.textContent = sql;
    sqlContainer.style.display = 'none';

    // 切換SQL顯示/隱藏
    sqlToggle.addEventListener('click', function() {
      sqlContainer.style.display = (sqlContainer.style.display === 'none') ? 'block' : 'none';
    });

    // 添加SQL相關元素到訊息
    messageDiv.appendChild(sqlActionsContainer);
    messageDiv.appendChild(sqlContainer);
  }

  // 添加完整訊息到聊天框
  chatBox.appendChild(messageDiv);
  chatBox.scrollTop = chatBox.scrollHeight;
}

//======================================================
// 圖表相關功能
//======================================================

/**
 * 顯示圖表加載動畫
 */
function showChartsLoading() {
  const loader = document.getElementById('chartsLoader');
  if (loader) {
    loader.classList.add('visible');
  }
}

/**
 * 隱藏圖表加載動畫
 */
function hideChartsLoading() {
  const loader = document.getElementById('chartsLoader');
  if (loader) {
    loader.classList.remove('visible');
  }
}

/**
 * 清空圖表容器
 */
function hideCharts() {
  const chartsContainer = document.getElementById('chartsContainer');
  if (chartsContainer) {
    chartsContainer.innerHTML = '';
  }
}

/**
 * 從API獲取並顯示圖表數據
 */
async function loadCharts() {
  try {
    // 從API獲取圖表數據
    const response = await fetch('/api/charts');
    const data = await response.json();
    
    // 準備圖表容器
    const chartsContainer = document.getElementById('chartsContainer');
    chartsContainer.innerHTML = '';
    chartsContainer.style.display = 'block';

    // 創建每個圖表的容器並添加圖表
    data.charts.forEach((chartData, index) => {
      const chartDiv = document.createElement('div');
      chartDiv.style.width = '100%';
      chartDiv.style.height = '400px';
      chartDiv.style.margin = '20px 0';
      chartDiv.style.borderRadius = '8px';
      chartDiv.style.background = '#fff';
      chartDiv.id = `chart-${index}`;
      chartsContainer.appendChild(chartDiv);

      // 處理圖片類型的圖表
      if (chartData.type === 'image') {
        const img = document.createElement('img');
        img.src = chartData.data;
        img.style.width = '100%';
        img.style.height = '100%';
        img.style.objectFit = 'contain';
        chartDiv.appendChild(img);
      }
      // 這裡可以添加其他類型圖表的處理...
    });
  } catch (error) {
    console.error('載入圖表失敗:', error);
  } finally {
    // 隱藏加載動畫
    hideChartsLoading();
  }
}

//======================================================
// 側欄圖表面板開關功能
//======================================================

// 側欄圖表面板切換
chartToggle.addEventListener('click', () => {
  chartPanel.classList.toggle('visible');
  container.classList.toggle('shifted');
});

//======================================================
// 初始歡迎訊息
//======================================================

// 顯示初始歡迎訊息
setTimeout(() => {
  appendMessage('bot', '您好，需要什麼幫助嗎?');
}, 4000);

//======================================================
// 資料表下拉選單功能
//======================================================

/**
 * 下拉選單展開/收起
 */
dropdownHeader.addEventListener('click', () => {
  filterDropdown.classList.toggle('open');
  dropdownSearch.value = '';
  filterDropdownSearch('');
});

/**
 * 選擇資料表並通知後端
 */
dropdownList.addEventListener('click', async (e) => {
  if (e.target.tagName.toLowerCase() === 'li') {
    // 獲取選中項的文本和值
    const selectedText = e.target.innerText;
    const selectedValue = e.target.getAttribute('data-value');
    
    // 更新選擇顯示並關閉下拉選單
    dropdownSelected.textContent = selectedText;
    filterDropdown.classList.remove('open');
    updateUserInputStatus();
    
    // 將選擇發送到後端
    try {
      const resp = await fetch('/select_table', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tableName: selectedValue })
      });
      const data = await resp.json();
      if (data.status === 'OK') {
        console.log('後端成功接收 tableName:', selectedValue);
      }
    } catch (error) {
      console.error('傳送選單資料失敗:', error);
    }
  }
});

/**
 * 下拉選單搜索過濾功能
 */
dropdownSearch.addEventListener('input', (e) => {
  filterDropdownSearch(e.target.value.trim().toLowerCase());
});

/**
 * 根據關鍵字過濾下拉選單項目
 * @param {string} keyword - 搜索關鍵字
 */
function filterDropdownSearch(keyword) {
  const items = dropdownList.querySelectorAll('li');
  items.forEach((item) => {
    const text = item.innerText.toLowerCase();
    item.style.display = text.includes(keyword) ? 'block' : 'none';
  });
}

// 點擊外部時關閉下拉選單
document.addEventListener('click', (e) => {
  if (!filterDropdown.contains(e.target) && !dropdownHeader.contains(e.target)) {
    filterDropdown.classList.remove('open');
  }
});



//使用者顯示相關功能////////////////////////////////////////////////////////////////////////

// 獲取使用者資訊
function fetchUserInfo() {
  fetch('/api/current_user')
      .then(response => response.json())
      .then(userInfo => {
          // 更新主要使用者資訊
          document.getElementById('userName').textContent = userInfo.username || 'Guest';
          document.getElementById('userHostname').textContent = userInfo.hostname || 'Unknown';
          
      })
      .catch(error => {
          console.error('Error fetching user info:', error);
          document.getElementById('userName').textContent = 'Guest';
          document.getElementById('userHostname').textContent = 'Unknown';
      });
}


document.addEventListener('DOMContentLoaded', function() {
  // 獲取使用者資訊
  fetchUserInfo();
});

//對話歷史紀錄相關功能////////////////////////////////////////////////////////////////////////
// 建立新的聊天 session
function createSession(){
  const sessionName = prompt("請輸入對話名稱：", "新對話");
  if(!sessionName) return;
  fetch('/create_session', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({session_name: sessionName})
  })
  .then(response => response.json())
  .then(data => {
    loadSessions();
    currentSessionId = data.session_id;
    document.getElementById('chat-history').innerHTML = '';
  });
}