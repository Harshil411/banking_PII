import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// BERT PII Extraction
export const extractPII = async (text, langHint = null) => {
  try {
    const response = await api.post('/api/bert/extract', {
      text,
      lang_hint: langHint,
    });
    return response.data;
  } catch (error) {
    throw new Error(error.response?.data?.detail || 'Failed to extract PII');
  }
};

// LLaMA PII Anonymization
export const anonymizePII = async (text, replacement = '[REDACTED]') => {
  try {
    const response = await api.post('/api/llama/anonymize', {
      text,
      replacement,
    });
    return response.data;
  } catch (error) {
    throw new Error(error.response?.data?.detail || 'Failed to anonymize PII');
  }
};

// Get metrics
export const getMetrics = async () => {
  try {
    const response = await api.get('/api/metrics');
    return response.data;
  } catch (error) {
    throw new Error(error.response?.data?.detail || 'Failed to fetch metrics');
  }
};

// Get data schema
export const getDataSchema = async () => {
  try {
    const response = await api.get('/api/data_schema');
    return response.data;
  } catch (error) {
    throw new Error(error.response?.data?.detail || 'Failed to fetch data schema');
  }
};

// Validated Enhanced PII Detection
export const validatedDetectPII = async (text, options = {}) => {
  try {
    const response = await api.post('/api/validated/detect', {
      text,
      use_regex: options.useRegex !== false,
      use_contextual: options.useContextual !== false,
      use_ml: options.useML !== false,
      min_confidence: options.minConfidence || 0.5,
    });
    return response.data;
  } catch (error) {
    throw new Error(error.response?.data?.detail || 'Failed to detect PII with validation');
  }
};

// Validated Enhanced PII Anonymization
export const validatedAnonymizePII = async (text, replacement = '[REDACTED]') => {
  try {
    const response = await api.post('/api/validated/anonymize', {
      text,
      replacement,
    });
    return response.data;
  } catch (error) {
    throw new Error(error.response?.data?.detail || 'Failed to anonymize PII with validation');
  }
};

export default api;
