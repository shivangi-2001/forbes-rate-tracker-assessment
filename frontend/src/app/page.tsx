import RatesTable from "@/components/RatesTable";
import RateHistoryChart from "@/components/RateHistoryChart";
import styles from "./page.module.css";

export default function Home() {
  return (
    <main>
      <header className={styles.header}>
        <div>
          <h1 className={styles.title}>Rate Tracker</h1>
          <p className={styles.subtitle}>
            Live interest rates — refreshed every 60 seconds
          </p>
        </div>
        <span className={styles.liveBadge}>● LIVE</span>
      </header>
      <RatesTable />
      <RateHistoryChart />
    </main>
  );
}
