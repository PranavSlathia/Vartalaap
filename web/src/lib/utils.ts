import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Get current date as YYYY-MM-DD in local (browser) timezone.
 * Use this instead of toISOString() which returns UTC.
 *
 * NOTE: This uses the browser's timezone, not the business timezone.
 * For MVP where admin and business are in the same timezone, this is fine.
 * For multi-timezone support, dates should be computed server-side or
 * the business timezone should be fetched from API and used here.
 *
 * @param date - Date to format (defaults to now)
 */
export function getLocalDateString(date: Date = new Date()): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}
