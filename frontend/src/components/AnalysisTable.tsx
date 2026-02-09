import React, { useMemo } from 'react';
import { AgGridReact } from 'ag-grid-react';
import { type ColDef } from 'ag-grid-community';
import { cn } from '../utils/cn';

interface AnalysisTableProps {
    data: any[];
    className?: string;
    onRowClick?: (data: any) => void;
}

export const AnalysisTable: React.FC<AnalysisTableProps> = ({ data, className, onRowClick }) => {
    const columnDefs = useMemo<ColDef[]>(() => {
        if (!data || data.length === 0) return [];

        // Dynamically generate columns based on first row
        const firstRow = data[0];
        return Object.keys(firstRow).map(key => {
            // Custom formatting based on column name
            let filter = 'agTextColumnFilter';
            let width = 120;

            if (key.includes('date') || key.includes('time')) {
                filter = 'agDateColumnFilter';
                width = 180;
            } else if (typeof firstRow[key] === 'number') {
                filter = 'agNumberColumnFilter';
                width = 100;
            } else if (typeof firstRow[key] === 'boolean') {
                width = 80;
            }

            return {
                field: key,
                headerName: key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
                filter: filter,
                sortable: true,
                resizable: true,
                width: width,
                // Hide some columns by default if needed
                hide: key.includes('details') || key.includes('raw')
            };
        });
    }, [data]);

    const defaultColDef = useMemo(() => ({
        sortable: true,
        filter: true,
        resizable: true,
    }), []);

    return (
        <div className={cn("ag-theme-quartz h-full w-full", className)}>
            <AgGridReact
                rowData={data}
                columnDefs={columnDefs}
                defaultColDef={defaultColDef}
                pagination={true}
                paginationPageSize={20}
                onRowClicked={(e) => onRowClick && onRowClick(e.data)}
                rowSelection="single"
                animateRows={true}
            />
        </div>
    );
};
