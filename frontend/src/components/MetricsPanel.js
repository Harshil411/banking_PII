import React, { useState, useEffect } from 'react';
import { getMetrics, getDataSchema } from '../services/api';

const MetricsPanel = () => {
  const [metrics, setMetrics] = useState(null);
  const [schema, setSchema] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const [metricsData, schemaResponse] = await Promise.all([
          getMetrics(),
          getDataSchema()
        ]);
        setMetrics(metricsData);
        // Handle the nested schema structure from backend
        setSchema(schemaResponse.schema || schemaResponse);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  const getCategoryIcon = (category) => {
    const icons = {
      'FULLNAME': '👤',
      'GIVENNAME': '👤',
      'SURNAME': '👤',
      'EMAIL': '📧',
      'TELEPHONENUM': '📞',
      'CITY': '🏙️',
      'STREET': '🛣️',
      'ZIPCODE': '📮',
      'DATE': '📅',
      'TIME': '⏰',
      'AGE': '🎂',
      'GENDER': '⚧',
      'AADHAAR': '🆔',
      'PAN': '💳',
      'VOTERID': '🗳️',
      'DRIVERLICENSENUM': '🚗',
      'ACCOUNTNUM': '🏦',
      'IFSC': '🏛️',
      'CREDITCARDNUM': '💳',
      'TRANSACTIONID': '🔄',
      'PASSPORTNUM': '📘',
      'BUILDINGNUM': '🏢'
    };
    return icons[category] || '📋';
  };

  const getCategoryDescription = (category) => {
    const descriptions = {
      'FULLNAME': 'Complete name of a person',
      'GIVENNAME': 'First name of a person',
      'SURNAME': 'Last name of a person',
      'EMAIL': 'Email address',
      'TELEPHONENUM': 'Phone number',
      'CITY': 'City name',
      'STREET': 'Street address',
      'ZIPCODE': 'Postal/ZIP code',
      'DATE': 'Date in various formats',
      'TIME': 'Time in various formats',
      'AGE': 'Age in years',
      'GENDER': 'Gender information',
      'AADHAAR': 'Indian Aadhaar number',
      'PAN': 'Indian PAN number',
      'VOTERID': 'Voter ID number',
      'DRIVERLICENSENUM': 'Driver license number',
      'ACCOUNTNUM': 'Bank account number',
      'IFSC': 'Indian Financial System Code',
      'CREDITCARDNUM': 'Credit card number',
      'TRANSACTIONID': 'Transaction reference ID',
      'PASSPORTNUM': 'Passport number',
      'BUILDINGNUM': 'Building number'
    };
    return descriptions[category] || 'Personal information';
  };

  const renderOverview = () => {
    if (!schema) return <div className="no-data">No data available</div>;

    const categories = Object.keys(schema);
    const totalCategories = categories.length;

    return (
      <div className="overview-section">
        <div className="overview-cards">
          <div className="overview-card">
            <div className="card-icon">📊</div>
            <div className="card-content">
              <h3>Total PII Categories</h3>
              <div className="card-value">{totalCategories}</div>
              <p>Different types of personal information detected</p>
            </div>
          </div>
          
          <div className="overview-card">
            <div className="card-icon">🔍</div>
            <div className="card-content">
              <h3>Detection Methods</h3>
              <div className="card-value">3</div>
              <p>Regex patterns, ML models, and contextual analysis</p>
            </div>
          </div>
          
          <div className="overview-card">
            <div className="card-icon">✅</div>
            <div className="card-content">
              <h3>Validation System</h3>
              <div className="card-value">Active</div>
              <p>Schema-based validation to filter false positives</p>
            </div>
          </div>
        </div>

        <div className="categories-summary">
          <h3>PII Categories Overview</h3>
          <div className="categories-grid">
            {categories.map((category) => {
              const categoryData = schema[category];
              const examples = categoryData?.examples || [];
              
              return (
                <div key={category} className="category-card">
                  <div className="category-header">
                    <span className="category-icon">{getCategoryIcon(category)}</span>
                    <span className="category-name">{category}</span>
                  </div>
                  <p className="category-description">{getCategoryDescription(category)}</p>
                  <div className="category-examples">
                    <strong>Examples:</strong> {examples.length > 0 ? examples.join(', ') : 'No examples available'}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    );
  };

  const renderSchemaDetails = () => {
    if (!schema) return <div className="no-data">No schema data available</div>;

    return (
      <div className="schema-details">
        <div className="schema-intro">
          <h3>📋 Data Schema Configuration</h3>
          <p>This schema defines the patterns and examples for each PII category that our system can detect and validate.</p>
        </div>

        <div className="schema-categories">
          {Object.entries(schema).map(([category, config]) => {
            const examples = config?.examples || [];
            const regex = config?.regex || 'No pattern available';
            
            return (
              <div key={category} className="schema-category">
                <div className="schema-category-header">
                  <span className="category-icon">{getCategoryIcon(category)}</span>
                  <h4>{category}</h4>
                  <span className="category-badge">PII Type</span>
                </div>
                
                <div className="schema-category-content">
                  <div className="schema-section">
                    <h5>📝 Examples</h5>
                    <div className="examples-list">
                      {examples.length > 0 ? (
                        examples.map((example, index) => (
                          <span key={index} className="example-tag">{example}</span>
                        ))
                      ) : (
                        <span className="example-tag">No examples available</span>
                      )}
                    </div>
                  </div>
                  
                  <div className="schema-section">
                    <h5>🔍 Pattern</h5>
                    <div className="pattern-display">
                      <code>{regex}</code>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  const renderMetricsDetails = () => {
    if (!metrics || Object.keys(metrics).length === 0) {
      return <div className="no-data">No metrics data available</div>;
    }

    return (
      <div className="metrics-details">
        <div className="metrics-intro">
          <h3>📊 System Performance Metrics</h3>
          <p>Detailed performance data and statistics from the PII detection system.</p>
        </div>

        {Object.entries(metrics).map(([file, data]) => (
          <div key={file} className="metrics-file">
            <div className="metrics-file-header">
              <h4>📄 {file}</h4>
              <span className="file-type">JSON Data</span>
            </div>
            
            <div className="metrics-content">
              <div className="json-viewer">
                <pre>{JSON.stringify(data, null, 2)}</pre>
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  };

  const renderRawData = () => {
    return (
      <div className="raw-data">
        <div className="raw-data-intro">
          <h3>🔧 Raw Data View</h3>
          <p>Raw JSON data for developers and technical users.</p>
        </div>

        <div className="raw-data-tabs">
          <div className="raw-data-section">
            <h4>📋 Data Schema (data_schema.json)</h4>
            <div className="json-viewer">
              <pre>{schema ? JSON.stringify(schema, null, 2) : 'No data available'}</pre>
            </div>
          </div>

          {metrics && Object.entries(metrics).map(([file, data]) => (
            <div key={file} className="raw-data-section">
              <h4>📊 {file}</h4>
              <div className="json-viewer">
                <pre>{JSON.stringify(data, null, 2)}</pre>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  };

  return (
    <div className="panel metrics-panel">
      <h2>📊 System Metrics & Schema</h2>
      
      {loading ? (
        <div className="output loading">
          <span className="loading-spinner"></span> Loading metrics and schema...
        </div>
      ) : error ? (
        <div className="output error">
          Error: {error}
        </div>
      ) : !schema ? (
        <div className="no-data">
          <h3>⚠️ No Data Available</h3>
          <p>Unable to load schema data. Please check if the backend is running and try again.</p>
        </div>
      ) : (
        <div className="metrics-container">
          <div className="metrics-tabs">
            <button 
              className={`tab-button ${activeTab === 'overview' ? 'active' : ''}`}
              onClick={() => setActiveTab('overview')}
            >
              📊 Overview
            </button>
            <button 
              className={`tab-button ${activeTab === 'schema' ? 'active' : ''}`}
              onClick={() => setActiveTab('schema')}
            >
              📋 Schema Details
            </button>
            <button 
              className={`tab-button ${activeTab === 'metrics' ? 'active' : ''}`}
              onClick={() => setActiveTab('metrics')}
            >
              📈 Performance
            </button>
            <button 
              className={`tab-button ${activeTab === 'raw' ? 'active' : ''}`}
              onClick={() => setActiveTab('raw')}
            >
              🔧 Raw Data
            </button>
          </div>

          <div className="metrics-content">
            {activeTab === 'overview' && renderOverview()}
            {activeTab === 'schema' && renderSchemaDetails()}
            {activeTab === 'metrics' && renderMetricsDetails()}
            {activeTab === 'raw' && renderRawData()}
          </div>
        </div>
      )}
    </div>
  );
};

export default MetricsPanel;