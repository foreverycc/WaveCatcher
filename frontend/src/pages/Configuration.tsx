import React, { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { stocksApi, analysisApi } from '../services/api';
import { Save, Trash2, Plus, RefreshCw, FileText, Settings, Edit2, Check, X, AlertTriangle, CheckCircle } from 'lucide-react';
import { cn } from '../utils/cn';
import ScoringConfigPanel from '../components/ScoringConfigPanel';
import { ReportSettingsPanel } from '../components/ReportSettingsPanel';

export const Configuration: React.FC = () => {
    const queryClient = useQueryClient();
    const [selectedFile, setSelectedFile] = useState<string | null>(null);
    const [fileContent, setFileContent] = useState<string>('');
    const [newFileName, setNewFileName] = useState('');
    const [newFileContent, setNewFileContent] = useState('');
    const [isCreating, setIsCreating] = useState(false);
    const [badTickers, setBadTickers] = useState<string[]>([]);
    const [validationMessage, setValidationMessage] = useState('');
    const [isValidating, setIsValidating] = useState(false);
    // Per-ticker weights (e.g. market cap) for the weighted breadth score
    const [showWeights, setShowWeights] = useState(false);
    const [weightsText, setWeightsText] = useState('');
    const [weightsMsg, setWeightsMsg] = useState('');
    const [weightsBusy, setWeightsBusy] = useState(false);
    const [cleanupTables, setCleanupTables] = useState<string[]>(['analysis_runs', 'analysis_results', 'price_history', 'option_chains']);
    const [isCleaningDb, setIsCleaningDb] = useState(false);

    // --- Index config state ---
    const [addingIndex, setAddingIndex] = useState(false);
    const [newIdxKey, setNewIdxKey] = useState('');
    const [newIdxSymbol, setNewIdxSymbol] = useState('');
    const [newIdxStockList, setNewIdxStockList] = useState('');
    const [newIdxWhitelist, setNewIdxWhitelist] = useState('');
    const [editingIdx, setEditingIdx] = useState<string | null>(null);
    const [editSymbol, setEditSymbol] = useState('');
    const [editStockList, setEditStockList] = useState('');
    const [editWhitelist, setEditWhitelist] = useState('');

    const { data: files, isLoading: isLoadingFiles } = useQuery({
        queryKey: ['stockFiles'],
        queryFn: stocksApi.list
    });

    const { data: selectedFileData } = useQuery({
        queryKey: ['stockFile', selectedFile],
        queryFn: () => selectedFile ? stocksApi.get(selectedFile) : null,
        enabled: !!selectedFile
    });

    // Fetch available indices
    const { data: indicesData } = useQuery({
        queryKey: ['availableIndices'],
        queryFn: async () => {
            const data = await analysisApi.getIndices();
            return data.indices;
        }
    });

    useEffect(() => {
        if (selectedFileData) {
            if (selectedFileData.content) {
                setFileContent(selectedFileData.content);
            } else {
                stocksApi.get(selectedFile!).then(data => {
                    if (data.content) setFileContent(data.content);
                });
            }
        }
        // Clear validation when file changes
        setBadTickers([]);
        setValidationMessage('');
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

    // --- Index CRUD mutations ---
    const parseWhitelist = (input: string): string[] => {
        return Array.from(new Set(
            input
                .split(/[\s,]+/)
                .map(s => s.trim().toUpperCase().replace('.', '-'))
                .filter(s => s.length > 0)
        ));
    };

    const upsertIndexMutation = useMutation({
        mutationFn: ({ key, symbol, stock_list, whitelist }: { key: string, symbol: string, stock_list: string, whitelist?: string[] }) =>
            analysisApi.upsertIndex(key, symbol, stock_list, whitelist),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['availableIndices'] });
            setAddingIndex(false);
            setEditingIdx(null);
            setNewIdxKey('');
            setNewIdxSymbol('');
            setNewIdxStockList('');
            setNewIdxWhitelist('');
        },
        onError: (error) => alert(`Error saving index: ${error}`)
    });

    const deleteIndexMutation = useMutation({
        mutationFn: (key: string) => analysisApi.deleteIndex(key),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['availableIndices'] });
        },
        onError: (error) => alert(`Error deleting index: ${error}`)
    });

    const listTickersOf = (content: string) =>
        content.split('\n').map(l => l.trim().toUpperCase()).filter(Boolean);

    const weightsToText = (weights: Record<string, number>) =>
        listTickersOf(fileContent)
            .map(t => weights[t] !== undefined ? `${t} ${Math.round(weights[t] * 1000) / 1000}` : `${t} `)
            .join('\n');

    const { data: savedWeights } = useQuery({
        queryKey: ['stockWeights', selectedFile],
        queryFn: () => stocksApi.getWeights(selectedFile!),
        enabled: !!selectedFile && showWeights
    });

    useEffect(() => {
        if (showWeights && savedWeights) {
            setWeightsText(weightsToText(savedWeights));
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [savedWeights, showWeights, selectedFile]);

    useEffect(() => { setShowWeights(false); setWeightsMsg(''); }, [selectedFile]);

    const parseWeights = (text: string) => {
        const out: Record<string, number> = {};
        for (const line of text.split('\n')) {
            const [t, v] = line.trim().split(/[\s,]+/);
            const num = Number(v);
            if (t && v !== undefined && v !== '' && Number.isFinite(num) && num >= 0) out[t.toUpperCase()] = num;
        }
        return out;
    };

    const parsedWeights = parseWeights(weightsText);
    const weightTotal = Object.values(parsedWeights).reduce((a, b) => a + b, 0);

    const handleSaveWeights = async () => {
        if (!selectedFile) return;
        setWeightsBusy(true);
        setWeightsMsg('');
        try {
            const saved = await stocksApi.saveWeights(selectedFile, parsedWeights);
            queryClient.setQueryData(['stockWeights', selectedFile], saved);
            queryClient.invalidateQueries({ queryKey: ['stockWeights'] });
            setWeightsMsg(`Saved weights for ${Object.keys(saved).length} tickers.`);
        } catch (err) {
            setWeightsMsg(`Save failed: ${err}`);
        } finally {
            setWeightsBusy(false);
        }
    };

    const handleFillMarketCap = async () => {
        if (!selectedFile) return;
        setWeightsBusy(true);
        setWeightsMsg('Fetching market caps from Yahoo Finance...');
        try {
            const res = await stocksApi.fillWeightsByMarketCap(selectedFile);
            queryClient.setQueryData(['stockWeights', selectedFile], res.weights);
            queryClient.invalidateQueries({ queryKey: ['stockWeights'] });
            setWeightsText(weightsToText(res.weights));
            setWeightsMsg(res.missing.length > 0
                ? `Saved market caps for ${Object.keys(res.weights).length} tickers; no market cap for ${res.missing.length}: ${res.missing.join(', ')} (weight 0 unless you set one)`
                : `Saved market caps for all ${Object.keys(res.weights).length} tickers.`);
        } catch (err) {
            setWeightsMsg(`Market cap fetch failed: ${err}`);
        } finally {
            setWeightsBusy(false);
        }
    };

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

    const startEdit = (idx: { key: string, symbol: string, stock_list: string, whitelist?: string[] }) => {
        setEditingIdx(idx.key);
        setEditSymbol(idx.symbol);
        setEditStockList(idx.stock_list);
        setEditWhitelist((idx.whitelist || []).join(', '));
    };

    const saveEdit = () => {
        if (editingIdx && editSymbol && editStockList) {
            upsertIndexMutation.mutate({
                key: editingIdx,
                symbol: editSymbol,
                stock_list: editStockList,
                whitelist: parseWhitelist(editWhitelist)
            });
        }
    };

    return (
        <div className="w-full p-4 md:p-8 max-w-6xl mx-auto space-y-8">
            <div className="flex justify-between items-center">
                <h2 className="text-3xl font-bold text-foreground">Configuration</h2>
            </div>

            {/* === Scoring Weights Section === */}
            <ReportSettingsPanel />
            <ScoringConfigPanel />

            {/* === Index Configuration Section === */}
            <div className="bg-card rounded-xl border border-border shadow-sm overflow-hidden">
                <div className="p-4 border-b border-border bg-muted/30 flex justify-between items-center">
                    <div>
                        <h3 className="font-semibold flex items-center gap-2">
                            <Settings className="w-4 h-4" /> Market Indices
                        </h3>
                        <p className="text-xs text-muted-foreground mt-0.5">
                            Manage index definitions and their whitelists. Whitelisted tickers are forcefully merged and preserved when fetching or updating stock lists.
                        </p>
                    </div>
                    <button
                        onClick={() => { setAddingIndex(!addingIndex); }}
                        className="p-1 hover:bg-muted rounded-md transition-colors"
                        title="Add Index"
                    >
                        <Plus className="w-5 h-5 text-primary" />
                    </button>
                </div>

                <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead className="bg-muted/10 text-muted-foreground text-xs">
                            <tr>
                                <th className="p-3 text-left font-medium">Key</th>
                                <th className="p-3 text-left font-medium">Symbol</th>
                                <th className="p-3 text-left font-medium">Stock List</th>
                                <th className="p-3 text-left font-medium">Whitelist (Always Retained)</th>
                                <th className="p-3 text-right font-medium w-24">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {indicesData?.map(idx => (
                                <tr key={idx.key} className="border-b last:border-0 hover:bg-muted/5">
                                    {editingIdx === idx.key ? (
                                        <>
                                            <td className="p-3 font-medium">{idx.key}</td>
                                            <td className="p-3">
                                                <input
                                                    type="text"
                                                    value={editSymbol}
                                                    onChange={e => setEditSymbol(e.target.value)}
                                                    className="w-full px-2 py-1 rounded border border-input bg-background text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                                                />
                                            </td>
                                            <td className="p-3">
                                                <select
                                                    value={editStockList}
                                                    onChange={e => setEditStockList(e.target.value)}
                                                    className="w-full px-2 py-1 rounded border border-input bg-background text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                                                >
                                                    {files?.map(f => (
                                                        <option key={f} value={f}>{f}</option>
                                                    ))}
                                                </select>
                                            </td>
                                            <td className="p-3">
                                                <input
                                                    type="text"
                                                    value={editWhitelist}
                                                    onChange={e => setEditWhitelist(e.target.value)}
                                                    placeholder="e.g. FUTU, LI, NIO, XPEV"
                                                    className="w-full px-2 py-1 rounded border border-input bg-background text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary"
                                                />
                                            </td>
                                            <td className="p-3 text-right">
                                                <div className="flex justify-end gap-1">
                                                    <button onClick={saveEdit} className="p-1 text-green-600 hover:bg-green-500/10 rounded" title="Save">
                                                        <Check className="w-4 h-4" />
                                                    </button>
                                                    <button onClick={() => setEditingIdx(null)} className="p-1 text-muted-foreground hover:bg-muted rounded" title="Cancel">
                                                        <X className="w-4 h-4" />
                                                    </button>
                                                </div>
                                            </td>
                                        </>
                                    ) : (
                                        <>
                                            <td className="p-3 font-medium">{idx.key}</td>
                                            <td className="p-3 text-muted-foreground">{idx.symbol}</td>
                                            <td className="p-3 text-muted-foreground">{idx.stock_list}</td>
                                            <td className="p-3">
                                                {idx.whitelist && idx.whitelist.length > 0 ? (
                                                    <div className="flex flex-wrap gap-1 max-w-sm">
                                                        {idx.whitelist.map(ticker => (
                                                            <span
                                                                key={ticker}
                                                                className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-mono font-medium bg-primary/10 text-primary border border-primary/20"
                                                            >
                                                                {ticker}
                                                            </span>
                                                        ))}
                                                    </div>
                                                ) : (
                                                    <span className="text-muted-foreground text-xs italic">None</span>
                                                )}
                                            </td>
                                            <td className="p-3 text-right">
                                                <div className="flex justify-end gap-1">
                                                    <button onClick={() => startEdit(idx)} className="p-1 text-muted-foreground hover:bg-muted hover:text-foreground rounded" title="Edit">
                                                        <Edit2 className="w-3.5 h-3.5" />
                                                    </button>
                                                    <button
                                                        onClick={() => { if (confirm(`Delete index "${idx.key}"?`)) deleteIndexMutation.mutate(idx.key); }}
                                                        className="p-1 text-muted-foreground hover:bg-red-500/10 hover:text-red-500 rounded"
                                                        title="Delete"
                                                    >
                                                        <Trash2 className="w-3.5 h-3.5" />
                                                    </button>
                                                </div>
                                            </td>
                                        </>
                                    )}
                                </tr>
                            ))}

                            {/* Add new row */}
                            {addingIndex && (
                                <tr className="border-b bg-primary/5">
                                    <td className="p-3">
                                        <input
                                            type="text"
                                            value={newIdxKey}
                                            onChange={e => setNewIdxKey(e.target.value.toUpperCase())}
                                            placeholder="e.g. SOXX"
                                            className="w-full px-2 py-1 rounded border border-input bg-background text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                                        />
                                    </td>
                                    <td className="p-3">
                                        <input
                                            type="text"
                                            value={newIdxSymbol}
                                            onChange={e => setNewIdxSymbol(e.target.value)}
                                            placeholder="e.g. SOXX"
                                            className="w-full px-2 py-1 rounded border border-input bg-background text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                                        />
                                    </td>
                                    <td className="p-3">
                                        <select
                                            value={newIdxStockList}
                                            onChange={e => setNewIdxStockList(e.target.value)}
                                            className="w-full px-2 py-1 rounded border border-input bg-background text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                                        >
                                            <option value="">Select stock list...</option>
                                            {files?.map(f => (
                                                <option key={f} value={f}>{f}</option>
                                            ))}
                                        </select>
                                    </td>
                                    <td className="p-3">
                                        <input
                                            type="text"
                                            value={newIdxWhitelist}
                                            onChange={e => setNewIdxWhitelist(e.target.value)}
                                            placeholder="e.g. FUTU, LI, NIO"
                                            className="w-full px-2 py-1 rounded border border-input bg-background text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary"
                                        />
                                    </td>
                                    <td className="p-3 text-right">
                                        <div className="flex justify-end gap-1">
                                            <button
                                                onClick={() => {
                                                    if (newIdxKey && newIdxSymbol && newIdxStockList) {
                                                        upsertIndexMutation.mutate({
                                                            key: newIdxKey,
                                                            symbol: newIdxSymbol,
                                                            stock_list: newIdxStockList,
                                                            whitelist: parseWhitelist(newIdxWhitelist)
                                                        });
                                                    }
                                                }}
                                                disabled={!newIdxKey || !newIdxSymbol || !newIdxStockList}
                                                className="p-1 text-green-600 hover:bg-green-500/10 rounded disabled:opacity-30"
                                                title="Add"
                                            >
                                                <Check className="w-4 h-4" />
                                            </button>
                                            <button onClick={() => setAddingIndex(false)} className="p-1 text-muted-foreground hover:bg-muted rounded" title="Cancel">
                                                <X className="w-4 h-4" />
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>


            {/* === Stock Lists Section === */}
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
                        <div className="space-y-4">
                            {/* Database Cleanup */}
                            <div>
                                <h4 className="text-sm font-medium mb-3 flex items-center gap-2">
                                    <Trash2 className="w-4 h-4 text-destructive" /> Database Cleanup
                                </h4>
                                <div className="grid grid-cols-2 gap-2 mb-3">
                                    {[
                                        { key: 'analysis_runs', label: 'Analysis Runs' },
                                        { key: 'analysis_results', label: 'Analysis Results' },
                                        { key: 'price_history', label: 'Price History' },
                                        { key: 'option_chains', label: 'Option Chains' },
                                    ].map(table => (
                                        <label key={table.key} className="flex items-center gap-2 cursor-pointer hover:bg-muted rounded px-2 py-1.5 text-sm">
                                            <input
                                                type="checkbox"
                                                checked={cleanupTables.includes(table.key)}
                                                onChange={(e) => {
                                                    if (e.target.checked) {
                                                        setCleanupTables([...cleanupTables, table.key]);
                                                    } else {
                                                        setCleanupTables(cleanupTables.filter((t: string) => t !== table.key));
                                                    }
                                                }}
                                                className="w-3.5 h-3.5 rounded border-input accent-destructive"
                                            />
                                            <span>{table.label}</span>
                                        </label>
                                    ))}
                                </div>
                                <button
                                    onClick={async () => {
                                        if (cleanupTables.length === 0) return;
                                        const tableLabels = cleanupTables.join(', ');
                                        if (!window.confirm(`This will delete all data from: ${tableLabels}. Continue?`)) return;
                                        setIsCleaningDb(true);
                                        try {
                                            const result = await analysisApi.cleanupDatabase(cleanupTables);
                                            const summary = Object.entries(result.deleted)
                                                .map(([table, count]) => `${table}: ${count} rows`)
                                                .join(', ');
                                            alert(`Database cleaned: ${summary}`);
                                        } catch (e) {
                                            alert('Failed to clean database.');
                                        } finally {
                                            setIsCleaningDb(false);
                                        }
                                    }}
                                    disabled={cleanupTables.length === 0 || isCleaningDb}
                                    className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-destructive/10 text-destructive rounded-lg hover:bg-destructive/20 transition-all font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                    {isCleaningDb ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                                    {isCleaningDb ? 'Cleaning...' : `Clean Selected (${cleanupTables.length}/4)`}
                                </button>
                            </div>
                        </div>
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
                                        placeholder={"AAPL\nMSFT\nGOOGL"}
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
                                <div className="flex gap-2 items-center">
                                    <div className="flex rounded-md border border-input overflow-hidden text-xs">
                                        <button
                                            onClick={() => setShowWeights(false)}
                                            className={cn("px-3 py-1.5", !showWeights ? "bg-primary text-primary-foreground" : "hover:bg-muted")}
                                        >Tickers</button>
                                        <button
                                            onClick={() => setShowWeights(true)}
                                            className={cn("px-3 py-1.5", showWeights ? "bg-primary text-primary-foreground" : "hover:bg-muted")}
                                            title="Per-ticker weights used by the Weighted Breadth Score"
                                        >Weights</button>
                                    </div>
                                    <button
                                        onClick={handleDelete}
                                        className="p-2 text-destructive hover:bg-destructive/10 rounded-md transition-colors"
                                        title="Delete File"
                                    >
                                        <Trash2 className="w-4 h-4" />
                                    </button>
                                </div>
                            </div>
                            {showWeights ? (
                                <>
                                    <div className="px-4 py-2 text-xs text-muted-foreground border-b border-border">
                                        One line per ticker: <span className="font-mono">TICKER weight</span>. Any scale works (e.g. market cap); the Weighted Breadth Score uses each ticker's share of the list total. Tickers without a weight count as 0.
                                    </div>
                                    <textarea
                                        value={weightsText}
                                        onChange={(e) => { setWeightsText(e.target.value); setWeightsMsg(''); }}
                                        className="flex-1 w-full p-4 bg-background focus:outline-none font-mono text-sm resize-none"
                                        placeholder={'AAPL 3450000000000\nMSFT 3100000000000'}
                                    />
                                    {weightsMsg && (
                                        <div className="px-4 py-2 text-sm border-t border-border text-muted-foreground">{weightsMsg}</div>
                                    )}
                                    <div className="p-4 border-t border-border bg-muted/30 flex justify-between items-center">
                                        <div className="text-xs text-muted-foreground">
                                            {Object.keys(parsedWeights).length} / {listTickersOf(fileContent).length} tickers weighted
                                            {weightTotal > 0 && (() => {
                                                const top = Object.entries(parsedWeights).sort((x, y) => y[1] - x[1]).slice(0, 3);
                                                return <> · top: {top.map(([t, v]) => `${t} ${(v / weightTotal * 100).toFixed(1)}%`).join(', ')}</>;
                                            })()}
                                        </div>
                                        <div className="flex gap-2">
                                            <button
                                                onClick={handleFillMarketCap}
                                                disabled={weightsBusy}
                                                className="px-4 py-2 rounded-md border border-input hover:bg-muted transition-colors flex items-center gap-2 text-sm"
                                            >
                                                {weightsBusy ? <RefreshCw className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
                                                Fill by Market Cap
                                            </button>
                                            <button
                                                onClick={handleSaveWeights}
                                                disabled={weightsBusy}
                                                className="px-4 py-2 rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors flex items-center gap-2"
                                            >
                                                <Save className="w-4 h-4" />
                                                Save Weights
                                            </button>
                                        </div>
                                    </div>
                                </>
                            ) : (<>
                            <div className="p-0 flex-1 flex flex-col min-h-0">
                                <textarea
                                    value={fileContent}
                                    onChange={(e) => { setFileContent(e.target.value); setBadTickers([]); setValidationMessage(''); }}
                                    className={cn(
                                        "flex-1 w-full p-4 bg-background focus:outline-none font-mono text-sm resize-none",
                                        badTickers.length > 0 ? "hidden" : ""
                                    )}
                                />
                                {badTickers.length > 0 && (
                                    <div className="flex-1 overflow-y-auto p-4 font-mono text-sm space-y-0.5">
                                        {fileContent.split('\n').map((line, i) => {
                                            const ticker = line.trim().toUpperCase();
                                            const isBad = ticker && badTickers.includes(ticker);
                                            return (
                                                <div
                                                    key={i}
                                                    className={cn(
                                                        "px-2 py-0.5 rounded",
                                                        isBad ? "bg-red-500/15 text-red-600 font-semibold" : ""
                                                    )}
                                                >
                                                    {line || '\u00A0'}
                                                </div>
                                            );
                                        })}
                                    </div>
                                )}
                            </div>
                            {validationMessage && (
                                <div className={cn(
                                    "px-4 py-2 text-sm border-t border-border flex items-center gap-2",
                                    badTickers.length > 0 ? "text-red-600 bg-red-500/5" : "text-green-600 bg-green-500/5"
                                )}>
                                    {badTickers.length > 0
                                        ? <AlertTriangle className="w-4 h-4 shrink-0" />
                                        : <CheckCircle className="w-4 h-4 shrink-0" />}
                                    <span>{validationMessage}</span>
                                </div>
                            )}
                            <div className="p-4 border-t border-border bg-muted/30 flex justify-between items-center">
                                <div className="text-xs text-muted-foreground">
                                    {fileContent.split('\n').filter(l => l.trim()).length} stocks
                                </div>
                                <div className="flex gap-2">
                                    <button
                                        onClick={async () => {
                                            const tickers = fileContent.split('\n').map(l => l.trim().toUpperCase()).filter(Boolean);
                                            if (tickers.length === 0) return;
                                            setIsValidating(true);
                                            setBadTickers([]);
                                            setValidationMessage('');
                                            try {
                                                const result = await stocksApi.validateTickers(tickers);
                                                setBadTickers(result.bad_tickers);
                                                if (result.bad_tickers.length > 0) {
                                                    setValidationMessage(
                                                        `${result.bad_tickers.length} bad ticker(s): ${result.bad_tickers.join(', ')}`
                                                    );
                                                } else {
                                                    setValidationMessage('All tickers are valid!');
                                                }
                                            } catch (err) {
                                                setValidationMessage(`Validation error: ${err}`);
                                            } finally {
                                                setIsValidating(false);
                                            }
                                        }}
                                        disabled={isValidating}
                                        className="px-4 py-2 rounded-md border border-input hover:bg-muted transition-colors flex items-center gap-2 text-sm"
                                    >
                                        {isValidating ? <RefreshCw className="w-4 h-4 animate-spin" /> : <AlertTriangle className="w-4 h-4" />}
                                        {isValidating ? 'Validating...' : 'Validate Tickers'}
                                    </button>
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
                            </>)}
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
