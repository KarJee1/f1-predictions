// Shapes of the JSON documents the backend publishes (see pipeline/f1pred/publish.py).

export type Sessions = {
  fp1: string | null;
  fp2: string | null;
  fp3: string | null;
  quali: string | null;
  sprint_quali?: string | null;
  sprint: string | null;
};

export type RaceInfo = {
  season: number;
  round: number;
  race_name: string;
  circuit_id: string;
  circuit_name: string;
  locality: string | null;
  country: string | null;
  race_start: string | null;
  sessions: Sessions;
};

export type Stage = 'pre' | 'practice' | 'quali';

export type Factor = { feature: string; text: string; impact: number };

export type DriverPrediction = {
  driver_id: string;
  code: string;
  number: string | null;
  first_name: string;
  last_name: string;
  team_id: string;
  team_name: string;
  team_color: string | null;
  grid: number | null;
  win_pct: number;
  podium_pct: number;
  points_pct: number;
  dnf_pct: number;
  expected_position: number;
  expected_points: number;
  position_distribution: number[];
  predicted_position: number;
  summary: string;
  factors: Factor[];
};

export type Prediction = {
  race: RaceInfo;
  stage: Stage;
  generated_at: string;
  model: string;
  weather: { rain_prob: number | null; air_temp_c: number | null } | null;
  drivers: DriverPrediction[];
};

export type Meta = {
  generated_at: string;
  season: number;
  next_race: RaceInfo;
  prediction_path: string;
  prediction_stage: Stage | null;
  last_race: RaceInfo | null;
  last_results_path: string | null;
};

export type ResultRow = {
  position: number;
  classified: boolean;
  driver_id: string;
  code: string | null;
  first_name: string;
  last_name: string;
  team_id: string;
  team_name: string;
  grid: number | null;
  status: string;
  points: number;
};

export type Results = { race: RaceInfo; results: ResultRow[] };

type StandingBase = {
  team_id: string | null;
  team_name: string | null;
  team_color: string | null;
  position: number;
  points: number;
  wins: number;
  predicted_points: number;
  predicted_position: number;
  position_change: number;
};

export type DriverStanding = StandingBase & {
  driver_id: string;
  code: string | null;
  first_name: string;
  last_name: string;
};

export type TeamStanding = StandingBase;

export type Standings = {
  generated_at: string;
  after_race: RaceInfo | null;
  drivers: DriverStanding[];
  constructors: TeamStanding[];
};

export type AccuracyRace = {
  round: number;
  race_name: string;
  stage: Stage;
  winner_correct: boolean;
  podium_hits: number;
  spearman: number;
  mean_abs_position_error: number;
  winner_log_loss?: number;
  predicted_top3: string[];
  actual_top3: string[];
  backfilled?: boolean;
};

export type Accuracy = {
  season: number;
  races: AccuracyRace[];
  summary: { races: number; winner_correct_pct: number; avg_podium_hits: number; avg_spearman: number };
};

export type NewsItem = {
  title: string;
  url: string;
  source: string;
  published_at: string;
  summary: string;
  image: string | null;
};

export type News = { generated_at: string; items: NewsItem[] };
