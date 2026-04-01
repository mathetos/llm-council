/**
 * API client for the LLM Council backend.
 */

const API_BASE =
  import.meta.env.VITE_API_BASE || 'http://localhost:8001';

export const api = {
  /**
   * List model pairing settings metadata.
   */
  async listModelPairings() {
    const response = await fetch(`${API_BASE}/api/settings/model-pairings`);
    if (!response.ok) {
      throw new Error('Failed to list model pairings');
    }
    return response.json();
  },

  /**
   * Probe all models in a selected pairing.
   */
  async testModelPairing(modelPairingId, freeBackupModelsOverride = null) {
    const response = await fetch(`${API_BASE}/api/settings/test-pairing`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model_pairing_id: modelPairingId || null,
        free_backup_models_override: freeBackupModelsOverride,
      }),
    });
    if (!response.ok) {
      throw new Error('Failed to test model pairing');
    }
    return response.json();
  },

  /**
   * Get model eligibility for a pairing from /models/user filtering.
   */
  async getModelPairingEligibility(modelPairingId) {
    const response = await fetch(
      `${API_BASE}/api/settings/model-pairings/${modelPairingId}/eligibility`
    );
    if (!response.ok) {
      throw new Error('Failed to load model eligibility');
    }
    return response.json();
  },

  /**
   * Get runtime resolution diagnostics for transparent substitution/fallback.
   */
  async getModelPairingDiagnostics(modelPairingId) {
    const response = await fetch(
      `${API_BASE}/api/settings/model-pairings/${modelPairingId}/diagnostics`
    );
    if (!response.ok) {
      throw new Error('Failed to load model pairing diagnostics');
    }
    return response.json();
  },

  /**
   * List free models currently eligible for this key.
   */
  async getEligibleFreeModels() {
    const response = await fetch(`${API_BASE}/api/settings/free-models`);
    if (!response.ok) {
      throw new Error('Failed to load eligible free models');
    }
    return response.json();
  },

  /**
   * List privacy-safe models for manual role assignment.
   */
  async getPrivacySafeModels() {
    const response = await fetch(`${API_BASE}/api/settings/privacy-safe-models`);
    if (!response.ok) {
      throw new Error('Failed to load privacy-safe models');
    }
    return response.json();
  },

  /**
   * Check one model slug for :free availability and eligibility.
   */
  async checkFreeVariant(modelId) {
    const response = await fetch(`${API_BASE}/api/settings/free-variant-check`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ model_id: modelId }),
    });
    if (!response.ok) {
      throw new Error('Failed to check free variant');
    }
    return response.json();
  },

  /**
   * List available profile guardrails.
   */
  async listProfiles() {
    const response = await fetch(`${API_BASE}/api/profiles`);
    if (!response.ok) {
      throw new Error('Failed to list profiles');
    }
    return response.json();
  },

  /**
   * List available local research packets for a profile.
   */
  async listProfilePackets(profileId) {
    const response = await fetch(`${API_BASE}/api/profiles/${profileId}/packets`);
    if (!response.ok) {
      throw new Error('Failed to list profile packets');
    }
    return response.json();
  },

  /**
   * List all conversations.
   */
  async listConversations() {
    const response = await fetch(`${API_BASE}/api/conversations`);
    if (!response.ok) {
      throw new Error('Failed to list conversations');
    }
    return response.json();
  },

  /**
   * Create a new conversation.
   */
  async createConversation() {
    const response = await fetch(`${API_BASE}/api/conversations`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({}),
    });
    if (!response.ok) {
      throw new Error('Failed to create conversation');
    }
    return response.json();
  },

  /**
   * Get a specific conversation.
   */
  async getConversation(conversationId) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}`
    );
    if (!response.ok) {
      throw new Error('Failed to get conversation');
    }
    return response.json();
  },

  /**
   * Delete a conversation.
   */
  async deleteConversation(conversationId) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}`,
      { method: 'DELETE' }
    );
    if (!response.ok) {
      throw new Error('Failed to delete conversation');
    }
    return response.json();
  },

  /**
   * Save a Stage 3 verdict as markdown.
   */
  async saveVerdictAsMarkdown(conversationId, assistantMessageIndex) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}/verdict`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ assistant_message_index: assistantMessageIndex }),
      }
    );
    if (!response.ok) {
      throw new Error('Failed to save verdict markdown');
    }
    return response.json();
  },

  /**
   * Start first-message interrogation and return question 1.
   */
  async startInterrogation(
    conversationId,
    content,
    profileId,
    packetId,
    modelPairingId,
    freeBackupModelsOverride = null
  ) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}/interrogation/start`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          content,
          profile_id: profileId,
          packet_id: packetId || null,
          model_pairing_id: modelPairingId || null,
          free_backup_models_override: freeBackupModelsOverride,
        }),
      }
    );
    if (!response.ok) {
      throw new Error('Failed to start interrogation');
    }
    return response.json();
  },

  /**
   * Submit one interrogation answer and receive next question or completion.
   */
  async submitInterrogationAnswer(conversationId, sessionId, answer) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}/interrogation/answer`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ session_id: sessionId, answer }),
      }
    );
    if (!response.ok) {
      throw new Error('Failed to submit interrogation answer');
    }
    return response.json();
  },

  /**
   * Send a message in a conversation.
   */
  async sendMessage(
    conversationId,
    content,
    interrogation = null,
    modelPairingId = null,
    roleAssignmentsOverride = null,
    freeBackupModelsOverride = null,
    rerunContextOverride = null
  ) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}/message`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          content,
          interrogation,
          model_pairing_id: modelPairingId,
          role_assignments_override: roleAssignmentsOverride,
          free_backup_models_override: freeBackupModelsOverride,
          rerun_context_override: rerunContextOverride,
        }),
      }
    );
    if (!response.ok) {
      throw new Error('Failed to send message');
    }
    return response.json();
  },

  /**
   * Send a message and receive streaming updates.
   * @param {string} conversationId - The conversation ID
   * @param {string} content - The message content
   * @param {function} onEvent - Callback function for each event: (eventType, data) => void
   * @returns {Promise<void>}
   */
  async sendMessageStream(
    conversationId,
    content,
    onEvent,
    interrogation = null,
    modelPairingId = null,
    roleAssignmentsOverride = null,
    freeBackupModelsOverride = null,
    rerunContextOverride = null,
    signal = undefined
  ) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}/message/stream`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          content,
          interrogation,
          model_pairing_id: modelPairingId,
          role_assignments_override: roleAssignmentsOverride,
          free_backup_models_override: freeBackupModelsOverride,
          rerun_context_override: rerunContextOverride,
        }),
        signal,
      }
    );

    if (!response.ok) {
      throw new Error('Failed to send message');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value);
      const lines = chunk.split('\n');

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6);
          try {
            const event = JSON.parse(data);
            onEvent(event.type, event);
          } catch (e) {
            console.error('Failed to parse SSE event:', e);
          }
        }
      }
    }
  },
};
