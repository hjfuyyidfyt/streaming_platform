import React from 'react';
import { Play, Clock, Eye } from 'lucide-react';
import { Link } from 'react-router-dom';
import { API_URL } from '../../services/api.js';

const VideoCard = ({ video }) => {
    // Helper to get correct thumbnail URL
    const getThumbnailUrl = () => {
        if (!video.thumbnail_url) return `${API_URL}/thumbnails/${video.id}`;
        if (video.thumbnail_url.startsWith('http')) return video.thumbnail_url;
        // If it was saved as /static/..., we map it to our new endpoint or just use path
        // For now, let's prefer the dynamic endpoint if the saved one looks like a path
        return `${API_URL}${video.thumbnail_url}`;
    };

    return (
        <Link to={`/video/${video.id}`} className="group relative bg-gray-800 rounded-lg overflow-hidden hover:scale-105 transition-transform duration-200 cursor-pointer shadow-lg block">
            <div className="relative aspect-video bg-gray-900">
                <img
                    src={getThumbnailUrl()}
                    alt={video.title}
                    className="w-full h-full object-cover"
                    loading="lazy"
                    onError={(e) => {
                        e.target.onerror = null;
                        e.target.src = `https://via.placeholder.com/640x360?text=${encodeURIComponent(video.title)}`;
                    }}
                />
                <div className="absolute inset-0 bg-black/20 group-hover:bg-black/0 transition-colors" />
                <span className="absolute bottom-2 right-2 bg-black/70 text-white text-xs px-1.5 py-0.5 rounded font-mono">
                    {video.duration ? new Date(video.duration * 1000).toISOString().substr(14, 5) : "00:00"}
                </span>
                <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                    <div className="bg-red-600 rounded-full p-3 shadow-lg transform scale-90 group-hover:scale-100 transition-transform">
                        <Play className="w-6 h-6 text-white fill-current" />
                    </div>
                </div>
            </div>

            <div className="p-3">
                <h3 className="text-white font-semibold text-sm line-clamp-2 leading-tight mb-1 group-hover:text-red-500 transition-colors">
                    {video.title}
                </h3>
                <div className="flex items-center text-gray-400 text-xs mt-2 space-x-3">
                    <div className="flex items-center">
                        <Eye className="w-3 h-3 mr-1" />
                        <span>{video.views?.toLocaleString()} views</span>
                    </div>
                    <div className="flex items-center px-2 py-0.5 rounded bg-gray-700/50">
                        <span className="text-[10px] uppercase font-bold tracking-wider">{video.category?.name || "Uncategorized"}</span>
                    </div>
                </div>
                <div className="text-gray-500 text-xs mt-1">
                    {new Date(video.upload_date).toLocaleDateString()}
                </div>
            </div>
        </Link>
    );
};

export default VideoCard;
