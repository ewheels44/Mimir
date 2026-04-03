import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import GraphPage from './pages/GraphPage';
import MetricsPage from './pages/MetricsPage';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<GraphPage />} />
        <Route path="/metrics" element={<MetricsPage />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);
