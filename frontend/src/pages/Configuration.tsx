import React, { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { stocksApi, analysisApi } from '../services/api';
import { Save, Trash2, Plus, RefreshCw, FileText } from 'lucide-react';
import { cn } from '../utils/cn';

export const Configuration: React.FC = () => {
    const queryClient = useQueryClient();
    const [selectedFile, setSelectedFile] = useState<string | null>(null);
    const [fileContent, setFileContent] = useState<string>('');
    const [newFileName, setNewFileName] = useState('');
    const [newFileContent, setNewFileContent] = useState('');
    const [isCreating, setIsCreating] = useState(false);

    const { data: files, isLoading: isLoadingFiles } = useQuery({
        queryKey: ['stockFiles'],
        queryFn: stocksApi.list
    });

    const { data: selectedFileData } = useQuery({
        queryKey: ['stockFile', selectedFile],
        queryFn: () => selectedFile ? stocksApi.get(selectedFile) : null,
        enabled: !!selectedFile
    });

    useEffect(() => {
        if (selectedFileData) {
            if (selectedFileData.content) {
                setFileContent(selectedFileData.content);
            } else {
                // Fallback if content is not in the initial response (though we added it)
                stocksApi.get(selectedFile!).then(data => {
                    if (data.content) setFileContent(data.content);
                });
            }
        }
    }, [selectedFileData, selectedFile]);

    const saveMutation = useMutation({
        mutationFn: (data: { filename: string, content: string }) =>
            stocksApi.update(data.filename, data.content),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['stockFile', selectedFile] });
            alert('Saved successfully!');
        },
        onError: (error) => alert(`Error saving: ${error}`)
    });

    const createMutation = useMutation({
        mutationFn: (data: { name: string, content: string }) =>
            stocksApi.create(data.name, data.content),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['stockFiles'] });
            setNewFileName('');
            setNewFileContent('');
            setIsCreating(false);
            alert('Created successfully!');
        },
        onError: (error) => alert(`Error creating: ${error}`)
    });

    const deleteMutation = useMutation({
        mutationFn: (filename: string) => stocksApi.delete(filename),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['stockFiles'] });
            setSelectedFile(null);
            setFileContent('');
            alert('Deleted successfully!');
        },
        onError: (error) => alert(`Error deleting: ${error}`)
    });

    const updateIndicesMutation = useMutation({
        mutationFn: analysisApi.updateIndices,
        onSuccess: (data) => {
            if (data.status === 'success') {
                alert('Indices updated successfully!\n' + (data.output || ''));
                queryClient.invalidateQueries({ queryKey: ['stockFiles'] });
            } else {
                alert('Failed to update indices: ' + data.message);
            }
        },
        onError: (error) => alert(`Error triggering update: ${error}`)
    });

    const handleSave = () => {
        if (selectedFile) {
            saveMutation.mutate({ filename: selectedFile, content: fileContent });
        }
    };

    const handleCreate = () => {
        if (newFileName && newFileContent) {
            createMutation.mutate({ name: newFileName, content: newFileContent });
        }
    };

    const handleDelete = () => {
        if (selectedFile && confirm(`Are you sure you want to delete ${selectedFile}?`)) {
            deleteMutation.mutate(selectedFile);
        }
    };

    return (
        <div className="p-8 max-w-6xl mx-auto space-y-8">
            <div className="flex justify-between items-center">
                <h2 className="text-3xl font-bold text-foreground">Configuration</h2>
            </div>

            <div className="grid grid-cols-12 gap-8">
                {/* Left Column */}
                <div className="col-span-4 flex flex-col gap-6 h-[600px]">
                    {/* File List */}
                    <div className="bg-card rounded-xl border border-border shadow-sm overflow-hidden flex flex-col flex-1 min-h-0">
                        <div className="p-4 border-b border-border bg-muted/30 flex justify-between items-center">
                            <h3 className="font-semibold flex items-center gap-2">
                                <FileText className="w-4 h-4" /> Stock Lists
                            </h3>
                            <button
                                onClick={() => setIsCreating(!isCreating)}
                                className="p-1 hover:bg-muted rounded-md transition-colors"
                                title="Create New"
                            >
                                <Plus className="w-5 h-5 text-primary" />
                            </button>
                        </div>

                        <div className="flex-1 overflow-y-auto p-2 space-y-1">
                            {isLoadingFiles ? (
                                <div className="p-4 text-center text-muted-foreground">Loading...</div>
                            ) : (
                                files?.map(file => (
                                    <button
                                        key={file}
                                        onClick={() => { setSelectedFile(file); setIsCreating(false); }}
                                        className={cn(
                                            "w-full text-left px-4 py-3 rounded-lg text-sm transition-colors flex items-center justify-between group",
                                            selectedFile === file
                                                ? "bg-primary/10 text-primary font-medium"
                                                : "hover:bg-muted text-muted-foreground hover:text-foreground"
                                        )}
                                    >
                                        {file}
                                    </button>
                                ))
                            )}
                        </div>
                    </div>

                    {/* System Maintenance */}
                    <div className="bg-card rounded-xl border border-border shadow-sm overflow-hidden p-4">
                        <h3 className="font-semibold mb-4 flex items-center gap-2">
                            <RefreshCw className="w-4 h-4" /> System Maintenance
                        </h3>
                        <button
                            onClick={() => updateIndicesMutation.mutate()}
                            disabled={updateIndicesMutation.isPending}
                            className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-secondary text-secondary-foreground rounded-lg hover:bg-secondary/80 transition-all font-medium disabled:opacity-50"
                        >
                            <RefreshCw className={cn("w-4 h-4", updateIndicesMutation.isPending ? "animate-spin" : "")} />
                            {updateIndicesMutation.isPending ? 'Updating...' : 'Update Indices (SP500, Nasdaq 100, Dow Jones, Russell 2000)'}
                        </button>
                    </div>
                </div>

                {/* Editor */}
                <div className="col-span-8 bg-card rounded-xl border border-border shadow-sm overflow-hidden flex flex-col h-[600px]">
                    {isCreating ? (
                        <div className="flex flex-col h-full">
                            <div className="p-4 border-b border-border bg-muted/30">
                                <h3 className="font-semibold">Create New Stock List</h3>
                            </div>
                            <div className="p-6 space-y-4 flex-1 overflow-y-auto">
                                <div>
                                    <label className="block text-sm font-medium mb-1">File Name (without extension)</label>
                                    <input
                                        type="text"
                                        value={newFileName}
                                        onChange={(e) => setNewFileName(e.target.value)}
                                        className="w-full px-3 py-2 rounded-md border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary/50"
                                        placeholder="e.g. my_stocks"
                                    />
                                </div>
                                <div className="flex-1 flex flex-col">
                                    <label className="block text-sm font-medium mb-1">Stock Symbols (one per line)</label>
                                    <textarea
                                        value={newFileContent}
                                        onChange={(e) => setNewFileContent(e.target.value)}
                                        className="flex-1 w-full px-3 py-2 rounded-md border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary/50 font-mono text-sm resize-none h-64"
                                        placeholder="AAPL&#10;MSFT&#10;GOOGL"
                                    />
                                </div>
                                <div className="flex justify-end gap-3">
                                    <button
                                        onClick={() => setIsCreating(false)}
                                        className="px-4 py-2 rounded-md border border-input hover:bg-muted transition-colors"
                                    >
                                        Cancel
                                    </button>
                                    <button
                                        onClick={handleCreate}
                                        disabled={createMutation.isPending}
                                        className="px-4 py-2 rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors flex items-center gap-2"
                                    >
                                        {createMutation.isPending ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                                        Create
                                    </button>
                                </div>
                            </div>
                        </div>
                    ) : selectedFile ? (
                        <div className="flex flex-col h-full">
                            <div className="p-4 border-b border-border bg-muted/30 flex justify-between items-center">
                                <h3 className="font-semibold">Editing: {selectedFile}</h3>
                                <div className="flex gap-2">
                                    <button
                                        onClick={handleDelete}
                                        className="p-2 text-destructive hover:bg-destructive/10 rounded-md transition-colors"
                                        title="Delete File"
                                    >
                                        <Trash2 className="w-4 h-4" />
                                    </button>
                                </div>
                            </div>
                            <div className="p-0 flex-1 flex flex-col">
                                <textarea
                                    value={fileContent}
                                    onChange={(e) => setFileContent(e.target.value)}
                                    className="flex-1 w-full p-4 bg-background focus:outline-none font-mono text-sm resize-none"
                                />
                            </div>
                            <div className="p-4 border-t border-border bg-muted/30 flex justify-between items-center">
                                <div className="text-xs text-muted-foreground">
                                    {fileContent.split('\n').filter(l => l.trim()).length} stocks
                                </div>
                                <button
                                    onClick={handleSave}
                                    disabled={saveMutation.isPending}
                                    className="px-4 py-2 rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors flex items-center gap-2"
                                >
                                    {saveMutation.isPending ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                                    Save Changes
                                </button>
                            </div>
                        </div>
                    ) : (
                        <div className="flex-1 flex items-center justify-center text-muted-foreground">
                            Select a file to edit or create a new one
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};
