export const API_URL = import.meta.env.PROD ? '' : 'http://localhost:8000';

// Helper to get auth headers
const getAuthHeaders = (token) => {
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    return headers;
};

export const api = {
    get: async (endpoint, token = null) => {
        try {
            const headers = token ? { 'Authorization': `Bearer ${token}` } : {};
            const response = await fetch(`${API_URL}${endpoint}`, { headers });
            if (!response.ok) {
                const err = await response.json().catch(() => ({}));
                throw new Error(err.detail || 'Request failed');
            }
            return await response.json();
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        }
    },

    post: async (endpoint, body, isFormData = false, token = null) => {
        try {
            const headers = isFormData
                ? (token ? { 'Authorization': `Bearer ${token}` } : {})
                : getAuthHeaders(token);
            const response = await fetch(`${API_URL}${endpoint}`, {
                method: 'POST',
                headers,
                body: isFormData ? body : JSON.stringify(body)
            });
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || 'Request failed');
            }
            return await response.json();
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        }
    },

    // ========== AUTH ==========
    login: async (email, password) => {
        const formData = new URLSearchParams();
        formData.append('username', email);
        formData.append('password', password);

        const response = await fetch(`${API_URL}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: formData
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'Login failed');
        }
        return await response.json();
    },

    register: async (username, email, password, displayName) => {
        return api.post('/auth/register', { username, email, password, display_name: displayName });
    },

    getMe: async (token) => api.get('/auth/me', token),

    // ========== VIDEOS ==========
    getVideos: (skip = 0, limit = 20) => api.get(`/videos/?skip=${skip}&limit=${limit}`),
    searchVideos: (query, skip = 0, limit = 20) => api.get(`/videos/search?q=${encodeURIComponent(query)}&skip=${skip}&limit=${limit}`),
    getVideosByCategory: (slug, skip = 0, limit = 20) => api.get(`/videos/category/${slug}?skip=${skip}&limit=${limit}`),
    getVideo: (id) => api.get(`/videos/${id}`),

    // Categories
    getCategories: () => api.get(`/videos/categories/all`),
    createCategory: (data) => api.post('/categories/', data),
    deleteCategory: (id) => fetch(`${API_URL}/categories/${id}`, { method: 'DELETE' }).then(r => r.json()),


    // Stream
    getStreamUrl: (videoId, resolution = null) => {
        const base = `${API_URL}/stream/${videoId}`;
        return resolution ? `${base}?resolution=${resolution}` : base;
    },
    getVideoResolutions: (videoId) => api.get(`/stream/${videoId}/resolutions`),
    recordView: (videoId) => api.post(`/videos/${videoId}/view`, {}),

    // Analytics
    getAnalyticsSummary: () => api.get('/analytics/summary'),
    getPopularVideos: () => api.get('/analytics/popular'),

    // ========== COMMENTS ==========
    getComments: (videoId, skip = 0, limit = 50) =>
        api.get(`/comments/video/${videoId}?skip=${skip}&limit=${limit}`),

    addComment: (videoId, content, parentId = null, superChat = null, token) => {
        const body = { video_id: videoId, content, parent_id: parentId };
        if (superChat) {
            body.is_super_chat = true;
            body.super_chat_amount = superChat.amount;
            body.super_chat_color = superChat.color;
        }
        return api.post('/comments/', body, false, token);
    },

    likeComment: (commentId, token) => api.post(`/comments/${commentId}/like`, {}, false, token),

    deleteComment: async (commentId, token) => {
        const response = await fetch(`${API_URL}/comments/${commentId}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
        });
        return response.json();
    },

    // ========== LIKES ==========
    likeVideo: (videoId, isLike = true, token) =>
        api.post(`/likes/video/${videoId}?is_like=${isLike}`, {}, false, token),

    getLikeStatus: (videoId, token = null) =>
        api.get(`/likes/video/${videoId}/status`, token),

    getLikedVideos: (token) => api.get('/likes/user/liked', token),

    // ========== HISTORY ==========
    saveProgress: (videoId, progressSeconds, completed = false, token) =>
        api.post('/history/', { video_id: videoId, progress_seconds: progressSeconds, completed }, false, token),

    getHistory: (token) => api.get('/history/', token),
    getContinueWatching: (token) => api.get('/history/continue', token),
    getVideoProgress: (videoId, token) => api.get(`/history/video/${videoId}`, token),
    clearHistory: async (token) => {
        const response = await fetch(`${API_URL}/history/`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
        });
        return response.json();
    },

    // ========== SUBSCRIPTIONS ==========
    toggleSubscribe: (channelId, token) => api.post(`/subscriptions/channel/${channelId}`, {}, false, token),
    async updateSubscription(channelId) {
        const response = await api.post(`/subscriptions/channel/${channelId}`);
        return response.data;
    },
    getSubscriptionStatus: (channelId, token) => api.get(`/subscriptions/channel/${channelId}/status`, token),
    getSubscriberCount: (channelId) => api.get(`/subscriptions/channel/${channelId}/count`),
    getSubscriptionFeed: (token, skip = 0, limit = 20) => api.get(`/subscriptions/feed?skip=${skip}&limit=${limit}`, token),

    // ========== PLAYLISTS ==========
    getPlaylists: (token) => api.get('/playlists/', token),
    getPlaylist: (id, token = null) => api.get(`/playlists/${id}`, token),
    createPlaylist: (name, description, isPublic, token) =>
        api.post('/playlists/', { name, description, is_public: isPublic }, false, token),

    addToPlaylist: (playlistId, videoId, token) =>
        api.post(`/playlists/${playlistId}/add`, { video_id: videoId }, false, token),

    removeFromPlaylist: async (playlistId, videoId, token) => {
        const response = await fetch(`${API_URL}/playlists/${playlistId}/remove/${videoId}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
        });
        return response.json();
    },

    // Watch Later shortcuts
    getWatchLater: (token) => api.get('/playlists/watch-later/videos', token),
    toggleWatchLater: (videoId, token) => api.post(`/playlists/watch-later/add/${videoId}`, {}, false, token),

    // ========== USER VIDEOS ==========
    getMyVideos: async () => {
        const token = localStorage.getItem('token');
        return api.get('/upload/my-videos', token);
    },

    getUserVideos: (userId) => api.get(`/upload/user/${userId}/videos`),

    uploadVideo: async (formData) => {
        const token = localStorage.getItem('token');
        const response = await fetch(`${API_URL}/upload/video`, {
            method: 'POST',
            headers: token ? { 'Authorization': `Bearer ${token}` } : {},
            body: formData
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'Upload failed');
        }
        return response.json();
    },

    deleteVideo: async (videoId) => {
        const token = localStorage.getItem('token');
        const response = await fetch(`${API_URL}/upload/video/${videoId}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'Delete failed');
        }
        return response.json();
    },

    // ========== ADMIN STORAGE ==========
    getStorageStats: (token) => api.get('/admin/storage', token),
    cleanupStorage: (target, token) => fetch(`${API_URL}/admin/storage/cleanup?target=${target}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
    }).then(r => r.json()),

    // ========== ADMIN SETTINGS ==========
    getSystemSettings: (token) => api.get('/admin/settings', token),
    updateSystemSettings: (settings, token) => api.post('/admin/settings', settings, false, token),
};
