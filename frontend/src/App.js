import React, { useState } from 'react';
import BertPanel from './components/BertPanel';
import LlamaPanel from './components/LlamaPanel';
import MetricsPanel from './components/MetricsPanel';
import EnhancedPanel from './components/EnhancedPanel';
import './index.css';

function App() {
  const [activeTab, setActiveTab] = useState('enhanced');

  // Banking-focused sample texts
  const sampleTexts = [
    {
      id: 1,
      title: "Customer Account Opening",
      text: "Hello, main Rajesh Kumar hoon Mumbai se. Mera Aadhaar number 1234 5678 9012 hai aur mera PAN number AAAPA1234A hai. Mujhe ek savings account kholna hai. Mera mobile number 9876543210 hai aur email id hai rajesh.kumar@hdfc.com. Mera address hai 123, MG Road, Andheri West, Mumbai - 400058."
    },
    {
      id: 2,
      title: "Loan Application",
      text: "Main Priya Sharma hoon, Flat 45, Tower B, DLF Cyber City, Gurgaon - 122002 mein rehti hoon. Mera Aadhaar number 9876 5432 1098 hai aur mera PAN number XYZPT5678K hai. Mujhe ₹50,00,000 ka home loan chahiye. Aap mujhse 8765432109 par ya priya.sharma@icici.com par contact kar sakte ho. Mere pita ka naam Ram Prasad Sharma hai."
    },
    {
      id: 3,
      title: "Credit Card Application",
      text: "I am Amit Patel from Ahmedabad. My Aadhaar number is 5555 6666 7777 and PAN is AAAPP1234A. I work as a software engineer at Infosys. My salary is ₹8,00,000 per annum. Please contact me at 7654321098 or amit.patel@sbi.com. My address is 456, C.G. Road, Ahmedabad - 380006."
    },
    {
      "id": 4,
      "title": "Banking Transaction",
      "text": "Transfer ₹25,000 from my account 1234567890123456 to account 9876543210987654 belonging to Sunita Devi. The IFSC code is HDFC0001234. Please process this NEFT transfer immediately."
    }
    
  ];

  const handleSampleClick = (sampleText) => {
    // This will be handled by the individual panels
    window.dispatchEvent(new CustomEvent('sampleTextSelected', { detail: sampleText }));
  };

  return (
    <div className="App">
      <div className="container">
        {/* Modern Header */}
        <header className="modern-header">
          <div className="header-content">
            <h1>Banking PII Detection</h1>
            <p>Advanced AI-powered Personal Information Extraction and Anonymization</p>
          </div>
        </header>

        {/* Sample Text Buttons */}
        <div className="sample-texts-section">
          <h3>Sample Texts</h3>
          <div className="sample-buttons-grid">
            {sampleTexts.map((sample) => (
              <button
                key={sample.id}
                className="sample-text-btn"
                onClick={() => handleSampleClick(sample.text)}
                title={sample.title}
              >
                <div className="sample-text-content">
                  <div className="sample-text-title">{sample.title}</div>
                  <div className="sample-text-preview">{sample.text.substring(0, 80)}...</div>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Individual Model Tabs */}
        <nav className="model-tabs">
          <button 
            className={activeTab === 'enhanced' ? 'model-tab active' : 'model-tab'}
            onClick={() => setActiveTab('enhanced')}
          >
            <span className="tab-icon">🔍</span>
            <span className="tab-text">Enhanced Detection</span>
          </button>
          <button 
            className={activeTab === 'individual' ? 'model-tab active' : 'model-tab'}
            onClick={() => setActiveTab('individual')}
          >
            <span className="tab-icon">🤖</span>
            <span className="tab-text">Individual Models</span>
          </button>
          <button 
            className={activeTab === 'metrics' ? 'model-tab active' : 'model-tab'}
            onClick={() => setActiveTab('metrics')}
          >
            <span className="tab-icon">📊</span>
            <span className="tab-text">Metrics</span>
          </button>
        </nav>

        {/* Main Content */}
        <main className="main-content">
          {activeTab === 'enhanced' && <EnhancedPanel />}
          {activeTab === 'individual' && (
            <div className="models-grid">
              <BertPanel />
              <LlamaPanel />
            </div>
          )}
          {activeTab === 'metrics' && <MetricsPanel />}
        </main>

        <footer className="footer">
          <p>Powered by FastAPI + React • Enhanced Multi-Method Detection • BERT & LLaMA Models</p>
        </footer>
      </div>
    </div>
  );
}

export default App;
