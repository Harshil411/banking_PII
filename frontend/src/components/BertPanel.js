import React, { useState } from 'react';
import { extractPII, validatedDetectPII } from '../services/api';

const BertPanel = () => {
  const [text, setText] = useState('');
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

  const handleExtract = async () => {
    if (!text.trim()) {
      setError('Please enter some text to analyze');
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      let data;
      if (useValidated) {
        data = await validatedDetectPII(text, {
          useRegex: true,
          useContextual: true,
          useML: true,
          minConfidence: 0.5
        });
      } else {
        data = await extractPII(text);
      }
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const formatResults = (data) => {
    if (!data || !data.entities) return 'No entities found';

    // Handle validated detection results
    if (useValidated && data.filtered_entities) {
      const validEntities = data.entities || [];
      const filteredEntities = data.filtered_entities || [];
      const summary = data.summary || {};

      let output = `📊 Validated PII Detection Results:\n`;
      output += `✅ Valid entities: ${validEntities.length}\n`;
      output += `❌ Filtered false positives: ${filteredEntities.length}\n`;
      output += `🎯 Validation rate: ${(summary.validation_rate * 100).toFixed(1)}%\n\n`;

      // Show valid entities
      if (validEntities.length > 0) {
        const groupedValid = {};
        validEntities.forEach(entity => {
          const type = entity.entity_group || 'UNKNOWN';
          if (!groupedValid[type]) {
            groupedValid[type] = [];
          }
          groupedValid[type].push({
            word: entity.word,
            score: entity.score,
            method: entity.method || 'unknown'
          });
        });

        output += `✅ VALID DETECTIONS:\n`;
        Object.entries(groupedValid).forEach(([type, entities]) => {
          output += `🔍 ${type}:\n`;
          entities.forEach(entity => {
            const confidence = (entity.score * 100).toFixed(1);
            output += `   • ${entity.word} (${confidence}% confidence, ${entity.method})\n`;
          });
          output += '\n';
        });
      }

      // Show filtered entities
      if (filteredEntities.length > 0) {
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

        output += `❌ FILTERED FALSE POSITIVES:\n`;
        Object.entries(groupedFiltered).forEach(([type, entities]) => {
          output += `🔍 ${type}:\n`;
          entities.forEach(entity => {
            const confidence = (entity.score * 100).toFixed(1);
            output += `   • ${entity.word} (${confidence}% confidence) - ${entity.reason}\n`;
          });
          output += '\n';
        });
      }

      return output;
    }

    // Handle regular detection results
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

    // Format output
    let output = `📊 PII Detection Results (${data.entities.length} entities found):\n\n`;
    
    Object.entries(groupedEntities).forEach(([type, entities]) => {
      output += `🔍 ${type}:\n`;
      entities.forEach(entity => {
        const confidence = (entity.score * 100).toFixed(1);
        output += `   • ${entity.word} (${confidence}% confidence)\n`;
      });
      output += '\n';
    });

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
        <span className="model-badge">BERT</span>
        Extract PII Entities
      </h2>
      
      <div className="form-group">
        <label htmlFor="bert-text">Customer Message / Details</label>
        <textarea
          id="bert-text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Enter text containing PII (names, Aadhaar, PAN, phone numbers, etc.)"
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


      <div style={{ display: 'flex', gap: '10px', marginBottom: '20px' }}>
        <button 
          className="btn" 
          onClick={handleExtract} 
          disabled={loading || !text.trim()}
        >
          {loading && <span className="loading-spinner"></span>}
          {loading ? 'Extracting...' : 'Extract PII'}
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
            formatResults(result)
          ) : (
            'Loading...'
          )}
        </div>
      )}
    </div>
  );
};

export default BertPanel;
