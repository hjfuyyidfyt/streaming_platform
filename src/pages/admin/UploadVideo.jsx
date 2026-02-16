import React, { useState, useRef } from 'react';
import { useAuth } from '../../context/AuthContext.jsx';
import { api } from '../../services/api.js';
import { Upload, X, Check, FileVideo, AlertCircle, Image as ImageIcon } from 'lucide-react';

const UploadVideo = () => {
    const { user } = useAuth();
    const [dragActive, setDragActive] = useState(false);
    const [file, setFile] = useState(null);
    const [thumbnail, setThumbnail] = useState(null);
    const [uploading, setUploading] = useState(false);
    const [progress, setProgress] = useState(0);
    const [uploadMetrics, setUploadMetrics] = useState({
        speed: 0,
        uploaded: 0,
        total: 0
    });
    const [categories, setCategories] = useState([]);
    const [providers, setProviders] = useState([]);
    const [formData, setFormData] = useState({
        title: '',
        description: '',
        category: '', // will be ID
        storage_mode: 'streamtape', // Default to StreamTape as requested
        is_short: false
    });


    const fileInputRef = useRef(null);
    const thumbnailInputRef = useRef(null);

    const handleDrag = (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.type === "dragenter" || e.type === "dragover") {
            setDragActive(true);
        } else if (e.type === "dragleave") {
            setDragActive(false);
        }
    };

    React.useEffect(() => {
        const fetchCats = async () => {
            try {
                const cats = await api.getCategories();
                setCategories(cats || []);
                if (cats && cats.length > 0) {
                    setFormData(prev => ({ ...prev, category: cats[0].id }));
                }
            } catch (err) {
                console.error("Failed to fetch categories", err);
            }
        };

        fetchCats();
    }, []);

    // Fetch System Settings
    React.useEffect(() => {
        const fetchSettings = async () => {
            try {
                const settings = await api.getSystemSettings();
                if (settings) {
                    const activeProvs = Object.entries(settings.storage_providers)
                        .map(([key, val]) => ({ id: key, name: val.name, enabled: val.enabled }))
                        .filter(p => p.enabled);
                    setProviders(activeProvs);
                    setFormData(prev => ({ ...prev, storage_mode: settings.default_storage }));
                }
            } catch (error) {
                console.error("Failed to load settings", error);
            }
        };
        fetchSettings();
    }, []);

    const handleDrop = (e) => {
        e.preventDefault();
        e.stopPropagation();
        setDragActive(false);
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
            validateAndSetFile(e.dataTransfer.files[0]);
        }
    };

    const handleChange = (e) => {
        e.preventDefault();
        if (e.target.files && e.target.files[0]) {
            validateAndSetFile(e.target.files[0]);
        }
    };

    const validateAndSetFile = (selectedFile) => {
        if (!selectedFile.type.startsWith('video/')) {
            alert('Please upload a video file');
            return;
        }
        // Check size (e.g. 2GB max)
        if (selectedFile.size > 2 * 1024 * 1024 * 1024) {
            alert('File size exceeds 2GB limit');
            return;
        }
        setFile(selectedFile);
        // Auto-fill title if empty
        if (!formData.title) {
            setFormData(prev => ({ ...prev, title: selectedFile.name.replace(/\.[^/.]+$/, "") }));
        }
    };

    const handleThumbnailChange = (e) => {
        if (e.target.files && e.target.files[0]) {
            const selectedFile = e.target.files[0];
            if (!selectedFile.type.startsWith('image/')) {
                alert('Please upload an image file');
                return;
            }
            setThumbnail(selectedFile);
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!file) return;

        setUploading(true);
        setProgress(10); // Start progress

        try {
            const data = new FormData();
            data.append('file', file);
            data.append('title', formData.title);
            data.append('description', formData.description);
            data.append('description', formData.description);
            // data.append('category_slug', formData.category.toLowerCase()); // Deprecated
            data.append('category_id', formData.category);
            data.append('is_short', formData.is_short);
            // Step 2696 upload.py: category_id: int = Form(...),
            // We need to fetch categories to get ID.
            // For now I'll hardcode or fetch. 
            // Wait, existing code used `category_slug`.
            // Check Step 2696 upload.py line 127: `category_id: int = Form(...)`.
            // BEFORE it was `category_slug: str = Form("action")`.
            // I CHANGED IT TO category_id IN STEP 2696!
            // I MUST UPDATE FRONTEND TO SEND category_id.

            // I need to fetch categories in useEffect.
            // Or revert backend to accept slug.
            // Backend Step 2696 line 144: category_id=category_id.
            // If I send slug, backend will 422.

            // I will revert backend change or update frontend to fetch categories.
            // Frontend is better.

            // But wait, I'm in multi_replace for Frontend.
            // I'll assume for now I can pass `category_id`. 
            // I'll add `category_id` to data.
            // But I don't have the ID.

            // Actually, I should check `upload.py` again.
            // Line 127: `category_id: int = Form(...)`.
            // The previous code had logic to look up category by slug.
            // My edit in Step 2696 REMOVED that lookup logic and replaced it with direct ID?
            // "category_id: int = Form(...)" in arg list.
            // "category = session.exec(select(Category)...)" was removed?

            // Checked Step 2696 diff block.
            // I replaced `category_slug: str = Form("action")` with `category_id: int = Form(...)`.
            // AND I removed the lookup logic in the External Handler block (I just used `category_id`).
            // BUT in the Local Handler block (which I didn't verify closely), does it use `category_id`?
            // "category = session.exec(select(Category).where(Category.slug == category_slug.lower())).first()"
            // That line is in Local Handler.
            // If I changed the signature to `category_id`, the variable `category_slug` is NO LONGER AVAILABLE.
            // So Local Handler will CRASH (`NameError: name 'category_slug' is not defined`).

            // I BROKE LOCAL UPLOAD LOGIC in Step 2696!
            // I must fix `upload.py` to accept `category_id` OR `category_slug`.
            // Or fix Local Handler to use `category_id`.

            // I will fix `upload.py` first.
            // And Frontend needs to send `category_id`.

            // Let's fix `upload.py` to use `category_id` consistently.
            // And update Frontend to fetch categories.


            // I need to fix category_id sending.
            // I will fetch categories.


            // Add thumbnail if provided
            if (thumbnail) {
                data.append('thumbnail', thumbnail);
            }

            let lastLoaded = 0;
            let lastTime = Date.now();

            await api.uploadVideo(data, (progressInfo) => {
                const currentTime = Date.now();
                const timeDiff = (currentTime - lastTime) / 1000;

                console.log('Upload Event:', progressInfo);

                // Update metrics if it's the first update, or at least 200ms passed, or it's 100%
                if (lastLoaded === 0 || timeDiff > 0.2 || progressInfo.percent === 100) {
                    const bytesDiff = progressInfo.loaded - lastLoaded;
                    const speed = timeDiff > 0 ? bytesDiff / timeDiff : 0;

                    const newMetrics = {
                        speed: speed,
                        uploaded: progressInfo.loaded,
                        total: progressInfo.total || file.size
                    };

                    setUploadMetrics(newMetrics);

                    lastLoaded = progressInfo.loaded;
                    lastTime = currentTime;
                }

                setProgress(progressInfo.percent);
            });

            setProgress(100);
            alert('Upload Complete!');

            // Reset Form
            setFile(null);
            setThumbnail(null);
            setFormData({ title: '', description: '', category: categories[0]?.id || '', is_short: false });
        } catch (error) {
            console.error("Upload failed", error);
            alert(`Upload Failed: ${error.message}`);
        } finally {
            setUploading(false);
            setProgress(0);
        }
    };

    const removeFile = () => {
        setFile(null);
    };

    return (
        <div className="max-w-4xl mx-auto">
            <h2 className="text-2xl font-bold mb-6">Upload New Video</h2>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                {/* Left Column: File Upload Zone */}
                <div className="lg:col-span-2 space-y-6">
                    {/* Video Drag & Drop */}
                    <div
                        className={`relative border-2 border-dashed rounded-xl p-8 text-center transition-colors ${dragActive ? 'border-red-500 bg-red-500/10' : 'border-gray-700 hover:border-gray-500 bg-[#242424]'
                            } ${file ? 'border-green-500/50' : ''}`}
                        onDragEnter={handleDrag}
                        onDragLeave={handleDrag}
                        onDragOver={handleDrag}
                        onDrop={handleDrop}
                    >
                        {!file ? (
                            <div className="flex flex-col items-center justify-center space-y-4 py-8">
                                <div className="bg-gray-800 p-4 rounded-full">
                                    <Upload className="w-8 h-8 text-gray-400" />
                                </div>
                                <div>
                                    <p className="text-lg font-medium">Drag & drop your video here</p>
                                    <p className="text-gray-500 text-sm mt-1">or click to browse files</p>
                                </div>
                                <button
                                    type="button"
                                    onClick={() => fileInputRef.current.click()}
                                    className="bg-red-600 hover:bg-red-700 text-white px-6 py-2 rounded-lg font-medium transition-colors"
                                >
                                    Select Video
                                </button>
                            </div>
                        ) : (
                            <div className="flex items-center justify-between bg-gray-800/50 p-4 rounded-lg">
                                <div className="flex items-center space-x-4">
                                    <div className="bg-red-900/30 p-2 rounded">
                                        <FileVideo className="w-8 h-8 text-red-500" />
                                    </div>
                                    <div className="text-left">
                                        <div className="font-medium text-white truncate max-w-[200px]">{file.name}</div>
                                        <div className="text-gray-500 text-sm">{(file.size / (1024 * 1024)).toFixed(2)} MB</div>
                                    </div>
                                </div>
                                <button onClick={removeFile} className="p-2 hover:bg-gray-700 rounded-full transition-colors">
                                    <X className="w-5 h-5 text-gray-400" />
                                </button>
                            </div>
                        )}
                        <input
                            ref={fileInputRef}
                            type="file"
                            accept="video/*"
                            className="hidden"
                            onChange={handleChange}
                        />
                    </div>

                    {/* Meta Data Form */}
                    <div className="bg-[#242424] p-6 rounded-xl border border-gray-800 space-y-6">
                        <div>
                            <label className="block text-sm font-medium text-gray-400 mb-2">Video Title</label>
                            <input
                                type="text"
                                value={formData.title}
                                onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                                className="w-full bg-[#121212] border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-red-600 focus:ring-1 focus:ring-red-600"
                                placeholder="Enter a catchy title"
                            />
                        </div>

                        <div className="grid grid-cols-2 gap-6">
                            <div>
                                <label className="block text-sm font-medium text-gray-400 mb-2">Category</label>
                                <select
                                    value={formData.category}
                                    onChange={(e) => setFormData({ ...formData, category: parseInt(e.target.value) })}
                                    className="w-full bg-[#121212] border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-red-600"
                                >
                                    {categories.map(cat => (
                                        <option key={cat.id} value={cat.id}>{cat.name}</option>
                                    ))}
                                </select>
                            </div>
                        </div>

                        <div className="flex items-center gap-3 bg-[#121212] border border-gray-700 rounded-lg px-4 py-3 cursor-pointer hover:border-red-600 transition-colors" onClick={() => setFormData({ ...formData, is_short: !formData.is_short })}>
                            <input
                                type="checkbox"
                                checked={formData.is_short}
                                onChange={(e) => setFormData({ ...formData, is_short: e.target.checked })}
                                className="w-5 h-5 rounded border-gray-700 bg-gray-800 text-red-600 focus:ring-red-600"
                            />
                            <div>
                                <p className="text-sm font-medium text-white">Upload as Short</p>
                                <p className="text-xs text-gray-500">Vertical videos (9:16) work best.</p>
                            </div>
                        </div>

                        <div>
                            <label className="block text-sm font-medium text-gray-400 mb-2">Destinations</label>
                            <div className="w-full bg-[#121212] border border-gray-700 rounded-lg px-4 py-3 text-white">
                                <p className="text-sm font-medium mb-2 text-gray-400">Video will be uploaded to:</p>
                                <div className="flex flex-wrap gap-2">
                                    {providers.length > 0 ? (
                                        providers.map(p => (
                                            <span key={p.id} className="bg-red-500/20 text-red-400 px-2 py-1 rounded text-xs border border-red-500/30">
                                                {p.name}
                                            </span>
                                        ))
                                    ) : (
                                        <span className="text-gray-500 text-xs italic">No providers enabled (Default: Telegram)</span>
                                    )}
                                </div>
                            </div>
                            <p className="text-xs text-gray-500 mt-2">Configure destinations in Admin Settings.</p>
                        </div>

                        <div>
                            <label className="block text-sm font-medium text-gray-400 mb-2">Description</label>
                            <textarea
                                value={formData.description}
                                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                                className="w-full bg-[#121212] border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-red-600 h-32 resize-none"
                                placeholder="Describe your video..."
                            />
                        </div>
                    </div>
                </div>

                {/* Right Column: Thumbnail & Actions */}
                <div className="space-y-6">
                    <div className="bg-[#242424] p-6 rounded-xl border border-gray-800">
                        <label className="block text-sm font-medium text-gray-400 mb-4">Thumbnail</label>
                        <div
                            onClick={() => thumbnailInputRef.current.click()}
                            className="aspect-video bg-[#121212] border border-gray-700 border-dashed rounded-lg flex flex-col items-center justify-center cursor-pointer hover:border-gray-500 transition-colors relative overflow-hidden group"
                        >
                            {thumbnail ? (
                                <>
                                    <img src={URL.createObjectURL(thumbnail)} alt="Thumbnail" className="w-full h-full object-cover" />
                                    <div className="absolute inset-0 bg-black/50 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                                        <p className="text-white text-sm font-medium">Change Image</p>
                                    </div>
                                </>
                            ) : (
                                <>
                                    <ImageIcon className="w-8 h-8 text-gray-600 mb-2" />
                                    <span className="text-sm text-gray-500">Upload Image</span>
                                    <span className="text-xs text-gray-600 mt-1">1280x720 Rec.</span>
                                </>
                            )}
                        </div>
                        <input
                            ref={thumbnailInputRef}
                            type="file"
                            accept="image/*"
                            className="hidden"
                            onChange={handleThumbnailChange}
                        />
                    </div>

                    {uploading && (
                        <div className="bg-[#242424] p-6 rounded-xl border border-gray-800">
                            <div className="flex justify-between items-center mb-2">
                                <span className="text-sm font-medium text-white">Uploading...</span>
                                <span className="text-sm font-bold text-red-500">{progress}%</span>
                            </div>

                            <div className="w-full bg-gray-700 rounded-full h-2.5 mb-4 overflow-hidden">
                                <div
                                    className="bg-red-600 h-full rounded-full transition-all duration-300 relative"
                                    style={{ width: `${progress}%` }}
                                >
                                    <div className="absolute inset-0 bg-white/20 animate-[shimmer_2s_infinite]" />
                                </div>
                            </div>

                            <div className="grid grid-cols-2 gap-4 text-[11px] text-gray-400">
                                <div className="bg-black/30 p-2 rounded border border-gray-800/50">
                                    <p className="uppercase tracking-tighter text-[10px] text-gray-500 mb-0.5">Speed</p>
                                    <p className="font-mono text-white">
                                        {uploadMetrics.speed > 1024 * 1024
                                            ? `${(uploadMetrics.speed / (1024 * 1024)).toFixed(2)} MB/s`
                                            : `${(uploadMetrics.speed / 1024).toFixed(2)} KB/s`}
                                    </p>
                                </div>
                                <div className="bg-black/30 p-2 rounded border border-gray-800/50">
                                    <p className="uppercase tracking-tighter text-[10px] text-gray-500 mb-0.5">Progress</p>
                                    <p className="font-mono text-white whitespace-nowrap">
                                        {(uploadMetrics.uploaded / (1024 * 1024)).toFixed(1)} / {(uploadMetrics.total / (1024 * 1024)).toFixed(1)} MB
                                    </p>
                                </div>
                            </div>

                            <p className="text-[10px] text-center text-gray-500 mt-4 italic">
                                Please keep this page open until completion
                            </p>
                        </div>
                    )}

                    {!uploading && (
                        <button
                            onClick={handleSubmit}
                            disabled={!file}
                            className={`w-full py-3 rounded-lg font-bold text-lg shadow-lg transition-all ${file
                                ? 'bg-red-600 hover:bg-red-700 text-white hover:scale-[1.02]'
                                : 'bg-gray-800 text-gray-500 cursor-not-allowed'
                                }`}
                        >
                            Publish Video
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
};

export default UploadVideo;
