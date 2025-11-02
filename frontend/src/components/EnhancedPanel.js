import React, { useState } from 'react';

const EnhancedPanel = () => {
  const [text, setText] = useState('');
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [settings, setSettings] = useState({
    useRegex: true,
    useContextual: true,
    useML: true,
    minConfidence: 0.5
  });

  // Listen for sample text selection from main app
  React.useEffect(() => {
    const handleSampleText = (event) => {
      setText(event.detail);
      setResults(null);
      setError(null);
    };

    window.addEventListener('sampleTextSelected', handleSampleText);
    return () => window.removeEventListener('sampleTextSelected', handleSampleText);
  }, []);

  const handleDetect = async () => {
    if (!text.trim()) {
      setError('Please enter some text to analyze');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await fetch('/api/validated/detect', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          text: text,
          use_regex: settings.useRegex,
          use_contextual: settings.useContextual,
          use_ml: settings.useML,
          min_confidence: settings.minConfidence
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      setResults(data);
    } catch (err) {
      setError(`Detection failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleAnonymize = async () => {
    if (!text.trim()) {
      setError('Please enter some text to anonymize');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await fetch('/api/validated/anonymize', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          text: text,
          replacement: '[REDACTED]'
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      setResults(data);
    } catch (err) {
      setError(`Anonymization failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };


  const getCategoryColor = (category) => {
    const colors = {
      'FULLNAME': '#e74c3c',
      'GIVENNAME': '#e67e22', 
      'SURNAME': '#f39c12',
      'EMAIL': '#2ecc71',
      'TELEPHONENUM': '#3498db',
      'CITY': '#9b59b6',
      'STREET': '#1abc9c',
      'ZIPCODE': '#34495e',
      'DATE': '#e91e63',
      'TIME': '#ff5722',
      'AGE': '#795548',
      'GENDER': '#607d8b',
      'AADHAAR': '#ff9800',
      'PAN': '#4caf50',
      'VOTERID': '#2196f3',
      'DRIVERLICENSENUM': '#ffc107',
      'ACCOUNTNUM': '#ff5722',
      'IFSC': '#9c27b0',
      'CREDITCARDNUM': '#f44336',
      'TRANSACTIONID': '#673ab7',
      'PASSPORTNUM': '#00bcd4',
      'BUILDINGNUM': '#8bc34a'
    };
    return colors[category] || '#95a5a6';
  };

  return (
    <div className="enhanced-panel">
      <div className="panel-header">
        <h2>🔍 Enhanced PII Detection</h2>
        <p>Multi-method PII detection combining ML models, regex patterns, and contextual analysis with schema validation</p>
      </div>


      {/* Settings Section */}
      <div className="settings-section">
        <h3>⚙️ Detection Settings</h3>
        <div className="settings-grid">
          <label className="setting-item">
            <input
              type="checkbox"
              checked={settings.useRegex}
              onChange={(e) => setSettings({...settings, useRegex: e.target.checked})}
            />
            <span>🔍 Regex Patterns</span>
          </label>
          <label className="setting-item">
            <input
              type="checkbox"
              checked={settings.useContextual}
              onChange={(e) => setSettings({...settings, useContextual: e.target.checked})}
            />
            <span>🎯 Contextual Analysis</span>
          </label>
          <label className="setting-item">
            <input
              type="checkbox"
              checked={settings.useML}
              onChange={(e) => setSettings({...settings, useML: e.target.checked})}
            />
            <span>🤖 ML Models</span>
          </label>
          <label className="setting-item">
            <span>Min Confidence:</span>
            <input
              type="range"
              min="0"
              max="1"
              step="0.1"
              value={settings.minConfidence}
              onChange={(e) => setSettings({...settings, minConfidence: parseFloat(e.target.value)})}
            />
            <span>{Math.round(settings.minConfidence * 100)}%</span>
          </label>
        </div>
      </div>

      {/* Input Section */}
      <div className="form-group">
        <label htmlFor="enhanced-text">Customer Message / Details</label>
        <textarea
          id="enhanced-text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Enter text containing PII (names, Aadhaar, PAN, phone numbers, etc.)"
          rows="5"
        />
      </div>

      <div style={{ display: 'flex', gap: '10px', marginBottom: '20px' }}>
        <button 
          className="btn" 
          onClick={handleDetect} 
          disabled={loading || !text.trim()}
        >
          {loading && <span className="loading-spinner"></span>}
          {loading ? 'Detecting...' : 'Detect PII'}
        </button>
        <button 
          className="btn" 
          onClick={handleAnonymize}
          disabled={loading || !text.trim()}
        >
          {loading ? 'Anonymizing...' : 'Anonymize Text'}
        </button>
        <button 
          className="btn" 
          onClick={() => {
            setText('');
            setResults(null);
            setError(null);
          }}
          style={{ background: 'linear-gradient(45deg, #6b7280, #9ca3af)' }}
        >
          Clear All
        </button>
      </div>

      {error && (
        <div className="error">
          <strong>❌ Error:</strong> {error}
        </div>
      )}

      {results && (
        <div className="validation-results">
          <h3>📊 Detection Results</h3>
          
          {/* Summary Stats */}
          <div className="summary-stats">
            <div className="stat-item">
              <div className="stat-number">{results.summary?.total_entities || 0}</div>
              <div className="stat-label">Valid Entities</div>
            </div>
            <div className="stat-item">
              <div className="stat-number">{results.summary?.filtered_entities || 0}</div>
              <div className="stat-label">Filtered Out</div>
            </div>
            <div className="stat-item">
              <div className="stat-number">{results.summary?.categories_found?.length || 0}</div>
              <div className="stat-label">Categories</div>
            </div>
            <div className="stat-item">
              <div className="stat-number">
                {results.summary?.validation_rate ? 
                  Math.round(results.summary.validation_rate * 100) + '%' : '0%'}
              </div>
              <div className="stat-label">Validation Rate</div>
            </div>
          </div>

          {/* Valid Entities */}
          {results.entities && results.entities.length > 0 && (
            <div className="valid-entities">
              <h4>✅ Valid Entities ({results.entities.length})</h4>
              <div className="entities-list">
                {results.entities.map((entity, index) => (
                  <div key={index} className="entity-item">
                    <div className="entity-text">"{entity.word}"</div>
                    <div className="entity-details">
                      <span className="entity-category">
                        {entity.entity_group}
                      </span>
                      <span className="entity-score">
                        {(entity.score * 100).toFixed(1)}% confidence
                      </span>
                    </div>
                    {entity.validation && (
                      <div className="entity-reason">
                        {entity.validation.reason}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Filtered Entities */}
          {results.filtered_entities && results.filtered_entities.length > 0 && (
            <div className="filtered-entities">
              <h4>❌ Filtered Entities ({results.filtered_entities.length})</h4>
              <div className="entities-list">
                {results.filtered_entities.map((entity, index) => (
                  <div key={index} className="entity-item filtered">
                    <div className="entity-text">"{entity.word}"</div>
                    <div className="entity-details">
                      <span className="entity-category filtered">
                        {entity.entity_group}
                      </span>
                      <span className="entity-score">
                        {(entity.score * 100).toFixed(1)}% confidence
                      </span>
                    </div>
                    <div className="entity-reason">
                      {entity.filter_reason || entity.validation?.reason}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Anonymized Text */}
          {results.redacted && (
            <div className="anonymized-section">
              <h4>🛡️ Anonymized Text</h4>
              <div className="redacted">
                {results.redacted}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default EnhancedPanel;