export type TimeWindow = {
  earliest: string // "06:00"
  latest: string   // "22:00"
}

export type SearchFilters = {
  non_stop_only: boolean
  excluded_airlines: string[]
  outbound_departure_window: TimeWindow | null
  outbound_arrival_window: TimeWindow | null
  return_departure_window: TimeWindow | null
  return_arrival_window: TimeWindow | null
}

export type Traveler = {
  name: string
  origin_airport: string // IATA code e.g. "JFK"
  filters: SearchFilters
}

export type TripSubmission = {
  travelers: Traveler[]
  destinations: string[]  // IATA codes e.g. ["CUN", "MBJ"]
  outbound_date: string   // YYYY-MM-DD
  return_date: string     // YYYY-MM-DD
  default_filters: SearchFilters
}

export type FlightOption = {
  departure_time: string
  arrival_time: string
  duration_minutes: number
  stops: number
  airline: string
  flight_numbers: string[]
  price: number
}

export type TravelerFlight = {
  traveler_name: string
  origin: string
  outbound: FlightOption
  return: FlightOption
  total_price: number
  currency: string
}

export type GroupStats = {
  currency: string
  individual_totals: number[]
  total: number
  average: number
  median: number
  cheapest: number
  most_expensive: number
}

export type DestinationResult = {
  destination: string // IATA code
  destination_name: string
  traveler_flights: TravelerFlight[]
  group_stats: GroupStats
}

export type JobResult = {
  job_id: string
  status: 'pending' | 'running' | 'complete' | 'failed'
  completed_at: string | null
  error: string | null
  destinations: DestinationResult[]
}
