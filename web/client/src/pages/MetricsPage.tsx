import React from 'react';
import { Link } from 'react-router-dom';
import styles from './MetricsPage.module.css';

export default function MetricsPage() {
  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <h1 className={styles.heading}>Metrics</h1>
        <Link to="/" className={styles.backLink}>← Graph</Link>
      </header>
      <div className={styles.coming}>
        <span className={styles.comingIcon}>📊</span>
        <p className={styles.comingText}>Coming soon</p>
      </div>
    </div>
  );
}
