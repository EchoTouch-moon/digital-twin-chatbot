import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';

const API_BASE_URL = '';

export const usePersonas = () => {
  const [personas, setPersonas] = useState([]);
  const [selectedPersona, setSelectedPersona] = useState(null);
  const [memories, setMemories] = useState([]);
  const [userProfile, setUserProfile] = useState(null);
  const [memorySummaries, setMemorySummaries] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchPersonas = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await axios.get(`${API_BASE_URL}/api/personas`);
      setPersonas(response.data);
      if (response.data.length > 0 && !selectedPersona) {
        setSelectedPersona(response.data[0]);
      }
    } catch (err) {
      console.error('Failed to fetch personas:', err);
      setError('Failed to fetch personas');
    } finally {
      setIsLoading(false);
    }
  }, [selectedPersona]);

  const createPersona = useCallback(async (name, description = '', avatarUrl = '') => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await axios.post(`${API_BASE_URL}/api/personas`, {
        name,
        description,
        avatar_url: avatarUrl,
      });
      const newPersona = response.data;
      setPersonas((prev) => [...prev, newPersona]);
      if (!selectedPersona) {
        setSelectedPersona(newPersona);
      }
      return newPersona;
    } catch (err) {
      console.error('Failed to create persona:', err);
      setError(err.response?.data?.detail || 'Failed to create persona');
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, [selectedPersona]);

  const fetchMemories = useCallback(async (personaId) => {
    if (!personaId) return;
    try {
      const response = await axios.get(`${API_BASE_URL}/api/personas/${personaId}/memories`);
      setMemories(response.data);
    } catch (err) {
      console.error('Failed to fetch memories:', err);
      setMemories([]);
    }
  }, []);

  const fetchUserProfile = useCallback(async (personaId) => {
    if (!personaId) return;
    try {
      const response = await axios.get(`${API_BASE_URL}/api/personas/${personaId}/profile`);
      setUserProfile(response.data);
    } catch (err) {
      console.error('Failed to fetch user profile:', err);
      setUserProfile(null);
    }
  }, []);

  const fetchMemorySummaries = useCallback(async (personaId) => {
    if (!personaId) return;
    try {
      const response = await axios.get(`${API_BASE_URL}/api/personas/${personaId}/summaries`);
      setMemorySummaries(response.data);
    } catch (err) {
      console.error('Failed to fetch memory summaries:', err);
      setMemorySummaries([]);
    }
  }, []);

  const generateUserProfile = useCallback(async (personaId) => {
    if (!personaId) return;
    setIsLoading(true);
    try {
      await axios.post(`${API_BASE_URL}/api/personas/${personaId}/profile/generate`);
      // 重新获取用户画像和摘要
      await fetchUserProfile(personaId);
      await fetchMemorySummaries(personaId);
    } catch (err) {
      console.error('Failed to generate user profile:', err);
      setError('Failed to generate user profile');
    } finally {
      setIsLoading(false);
    }
  }, [fetchUserProfile, fetchMemorySummaries]);

  const selectPersona = useCallback((persona) => {
    setSelectedPersona(persona);
    if (persona?.id) {
      fetchMemories(persona.id);
      fetchUserProfile(persona.id);
      fetchMemorySummaries(persona.id);
    }
  }, [fetchMemories, fetchUserProfile, fetchMemorySummaries]);

  useEffect(() => {
    fetchPersonas();
  }, [fetchPersonas]);

  useEffect(() => {
    if (selectedPersona?.id) {
      fetchMemories(selectedPersona.id);
      fetchUserProfile(selectedPersona.id);
      fetchMemorySummaries(selectedPersona.id);
    }
  }, [selectedPersona?.id, fetchMemories, fetchUserProfile, fetchMemorySummaries]);

  return {
    personas,
    selectedPersona,
    memories,
    userProfile,
    memorySummaries,
    isLoading,
    error,
    fetchPersonas,
    createPersona,
    selectPersona,
    fetchMemories,
    generateUserProfile,
  };
};
