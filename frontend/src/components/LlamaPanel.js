import React, { useState } from 'react';
import { anonymizePII, validatedAnonymizePII } from '../services/api';

const LlamaPanel = () => {
  const [text, setText] = useState('');
  const [replacement, setReplacement] = useState('[REDACTED]');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [useValidated, setUseValidated] = useState(true);

  // Listen for sample text selection from main app
  React.useEffect(() => {
    const handleSampleText = (event) => {
      setText(event.detail);
      setResult(null);
      setError(null);
    };

    window.addEventListener('sampleTextSelected', handleSampleText);
    return () => window.removeEventListener('sampleTextSelected', handleSampleText);
  }, []);

  const handleAnonymize = async () => {
    if (!text.trim()) {
      setError('Please enter some text to anonymize');
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      let data;
      if (useValidated) {
        data = await validatedAnonymizePII(text, replacement);
      } else {
        data = await anonymizePII(text, replacement);
      }
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const formatAnonymizationResults = (data) => {
    if (!data) return 'No data available';

    let output = `🔒 PII Anonymization Results:\n\n`;
    
    // Handle validated anonymization results
    if (useValidated && data.filtered_entities) {
      const validEntities = data.entities || [];
      const filteredEntities = data.filtered_entities || [];
      const summary = data.summary || {};

      output += `📊 Validated Detection Results:\n`;
      output += `✅ Valid entities: ${validEntities.length}\n`;
      output += `❌ Filtered false positives: ${filteredEntities.length}\n`;
      output += `🎯 Validation rate: ${(summary.validation_rate * 100).toFixed(1)}%\n\n`;

      if (validEntities.length > 0) {
        const groupedValid = {};
        validEntities.forEach(entity => {
          const type = entity.entity_group || 'UNKNOWN';
          if (!groupedValid[type]) {
            groupedValid[type] = [];
          }
          groupedValid[type].push({
            word: entity.word,
            score: entity.score
          });
        });

        output += `✅ VALID DETECTIONS:\n`;
        Object.entries(groupedValid).forEach(([type, entities]) => {
          output += `🔍 ${type}:\n`;
          entities.forEach(entity => {
            const confidence = (entity.score * 100).toFixed(1);
            output += `   • ${entity.word} (${confidence}% confidence)\n`;
          });
        });
        output += '\n';
      }

      if (filteredEntities.length > 0) {
        output += `❌ FILTERED FALSE POSITIVES:\n`;
        const groupedFiltered = {};
        filteredEntities.forEach(entity => {
          const type = entity.entity_group || 'UNKNOWN';
          if (!groupedFiltered[type]) {
            groupedFiltered[type] = [];
          }
          groupedFiltered[type].push({
            word: entity.word,
            score: entity.score,
            reason: entity.filter_reason || 'Unknown reason'
          });
        });

        Object.entries(groupedFiltered).forEach(([type, entities]) => {
          output += `🔍 ${type}:\n`;
          entities.forEach(entity => {
            const confidence = (entity.score * 100).toFixed(1);
            output += `   • ${entity.word} (${confidence}% confidence) - ${entity.reason}\n`;
          });
        });
        output += '\n';
      }
    } else if (data.entities && data.entities.length > 0) {
      output += `📊 Detected ${data.entities.length} PII entities:\n`;
      
      // Group entities by type
      const groupedEntities = {};
      data.entities.forEach(entity => {
        const type = entity.entity_group || 'UNKNOWN';
        if (!groupedEntities[type]) {
          groupedEntities[type] = [];
        }
        groupedEntities[type].push({
          word: entity.word,
          score: entity.score
        });
      });

      Object.entries(groupedEntities).forEach(([type, entities]) => {
        output += `\n🔍 ${type}:\n`;
        entities.forEach(entity => {
          const confidence = (entity.score * 100).toFixed(1);
          output += `   • ${entity.word} (${confidence}% confidence)\n`;
        });
      });
    } else {
      output += `✅ No PII entities detected in the text.\n`;
    }

    output += `\n📝 Original Text:\n${data.original_text || text}\n\n`;
    output += `🔒 Anonymized Text:\n${data.redacted || data.anonymized || 'No anonymization applied'}`;

    return output;
  };

  const clearAll = () => {
    setText('');
    setResult(null);
    setError(null);
  };


  return (
    <div className="panel">
      <h2>
        <span className="model-badge">LLaMA</span>
        Anonymize PII
      </h2>
      
      <div className="form-group">
        <label htmlFor="llama-text">Transaction Narrative</label>
        <textarea
          id="llama-text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Enter text to anonymize (e.g., Customer complaint with Aadhaar, PAN, account numbers...)"
          rows="5"
        />
      </div>

      <div className="form-group">
        <label style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <input
            type="checkbox"
            checked={useValidated}
            onChange={(e) => setUseValidated(e.target.checked)}
            style={{ width: '18px', height: '18px' }}
          />
          <span>Use Validated Detection (Filters false positives)</span>
        </label>
      </div>


      <div className="form-group">
        <label htmlFor="replacement">Replacement Token</label>
        <input
          id="replacement"
          type="text"
          value={replacement}
          onChange={(e) => setReplacement(e.target.value)}
          placeholder="[REDACTED]"
        />
      </div>

      <div style={{ display: 'flex', gap: '10px', marginBottom: '20px' }}>
        <button 
          className="btn" 
          onClick={handleAnonymize} 
          disabled={loading || !text.trim()}
        >
          {loading && <span className="loading-spinner"></span>}
          {loading ? 'Anonymizing...' : 'Anonymize PII'}
        </button>
        <button 
          className="btn" 
          onClick={clearAll}
          style={{ background: 'linear-gradient(45deg, #6b7280, #9ca3af)' }}
        >
          Clear All
        </button>
      </div>

      {(result || error) && (
        <div className={`output ${loading ? 'loading' : error ? 'error' : ''}`}>
          {error ? (
            `Error: ${error}`
          ) : result ? (
            formatAnonymizationResults(result)
          ) : (
            'Loading...'
          )}
        </div>
      )}
    </div>
  );
};

export default LlamaPanel;
