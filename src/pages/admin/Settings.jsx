import React, { useEffect, useState } from 'react';
import { api } from '../../services/api.js';
import { useAuth } from '../../context/AuthContext.jsx';
import { Save, Server, Check } from 'lucide-react';

const Settings = () => {
    const { token } = useAuth();
    const [settings, setSettings] = useState(null);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        const fetchSettings = async () => {
            try {
                const data = await api.getSystemSettings(token);
                setSettings(data);
            } catch (err) {
                console.error(err);
            } finally {
                setLoading(false);
            }
        };
        fetchSettings();
    }, [token]);

    const handleToggle = (key) => {
        setSettings(prev => ({
            ...prev,
            storage_providers: {
                ...prev.storage_providers,
                [key]: {
                    ...prev.storage_providers[key],
                    enabled: !prev.storage_providers[key].enabled
                }
            }
        }));
    };

    const handleDefaultChange = (key) => {
        setSettings(prev => ({
            ...prev,
            default_storage: key
        }));
    };

    const handleSave = async () => {
        setSaving(true);
        try {
            await api.updateSystemSettings(settings, token);
            alert('Settings saved successfully');
        } catch (err) {
            console.error(err);
            alert('Failed to save settings');
        } finally {
            setSaving(false);
        }
    };

    if (loading) return <div className="text-white p-8">Loading settings...</div>;
    if (!settings) return <div className="text-white p-8">Error loading settings.</div>;

    return (
        <div className="text-white p-6 max-w-4xl">
            <h1 className="text-2xl font-bold mb-8 flex items-center gap-2">
                <Server className="w-6 h-6 text-red-500" />
                System Configuration
            </h1>

            <div className="bg-[#1a1a1a] border border-gray-800 rounded-xl p-6 mb-8">
                <h2 className="text-lg font-semibold mb-4">Video Upload Providers</h2>
                <div className="space-y-4">
                    {Object.entries(settings.storage_providers).map(([key, provider]) => (
                        <div key={key} className="flex items-center justify-between bg-[#242424] p-4 rounded-lg border border-gray-700/50">
                            <div className="flex items-center gap-4">
                                <div className={`w-3 h-3 rounded-full ${provider.enabled ? 'bg-green-500' : 'bg-gray-600'}`}></div>
                                <div>
                                    <p className="font-medium">{provider.name}</p>
                                    <p className="text-xs text-gray-500 capitalize">{key}</p>
                                </div>
                            </div>

                            <div className="flex items-center gap-6">
                                {/* Default Selector */}
                                <label className="flex items-center gap-2 cursor-pointer">
                                    <input
                                        type="radio"
                                        name="default_storage"
                                        checked={settings.default_storage === key}
                                        onChange={() => handleDefaultChange(key)}
                                        disabled={!provider.enabled}
                                        className="text-red-600 focus:ring-red-600 bg-gray-700 border-gray-600"
                                    />
                                    <span className={`text-sm ${settings.default_storage === key ? 'text-white' : 'text-gray-500'}`}>
                                        Default
                                    </span>
                                </label>

                                {/* Enable Toggle */}
                                <button
                                    onClick={() => handleToggle(key)}
                                    className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${provider.enabled
                                        ? 'bg-green-500/10 text-green-500 border border-green-500/50 hover:bg-green-500/20'
                                        : 'bg-gray-700 text-gray-400 hover:bg-gray-600'
                                        }`}
                                >
                                    {provider.enabled ? 'Enabled' : 'Disabled'}
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            <div className="flex justify-end">
                <button
                    onClick={handleSave}
                    disabled={saving}
                    className="flex items-center gap-2 bg-red-600 hover:bg-red-700 text-white px-6 py-2.5 rounded-lg font-bold shadow-lg transition-transform hover:scale-105"
                >
                    {saving ? (
                        <>Saving...</>
                    ) : (
                        <>
                            <Save className="w-4 h-4" /> Save Changes
                        </>
                    )}
                </button>
            </div>
        </div>
    );
};

export default Settings;
