import { promises as fs } from "node:fs";
import path from "node:path";
import { NextResponse } from "next/server";

type CsvRow = Record<string, string>;

const parseCsv = (raw: string): CsvRow[] => {
  const lines = raw
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  if (lines.length < 2) {
    return [];
  }

  const headers = lines[0].split(",").map((header) => header.trim());

  return lines.slice(1).map((line) => {
    const values = line.split(",").map((value) => value.trim());
    const row: CsvRow = {};

    headers.forEach((header, index) => {
      row[header] = values[index] ?? "";
    });

    return row;
  });
};

export async function GET() {
  try {
    const csvPath = path.join(process.cwd(), "demo-market-app", "mock.csv");
    const rawCsv = await fs.readFile(csvPath, "utf8");
    const rows = parseCsv(rawCsv);

    return NextResponse.json({ ok: true, rows });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to load mock.csv";
    return NextResponse.json({ ok: false, error: message, rows: [] }, { status: 500 });
  }
}
