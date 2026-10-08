-- Schéma de Kaldera (dossier 2.6 bis). Écarts consignés au journal : demandes.fiche,
-- demandes.numero_contrat nullable.

-- Fichiers : 1 ligne par contenu distinct (déduplication par empreinte)
CREATE TABLE blobs (
  sha256   text PRIMARY KEY CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  contenu  bytea NOT NULL,
  mime     text NOT NULL CHECK (mime IN ('application/pdf','image/png','image/jpeg')),
  taille   int  NOT NULL CHECK (taille BETWEEN 1 AND 10485760),
  recu_le  timestamptz NOT NULL DEFAULT now()
);

-- Termes contractuels extraits : 1 ligne par contrat, réutilisée par ses demandes
CREATE TABLE contrats (
  numero            text PRIMARY KEY,
  sha256            text NOT NULL REFERENCES blobs,
  formule           text CHECK (formule IN ('essentiel','confort','premium')),
  date_souscription date,
  franchise numeric(10,2) CHECK (franchise >= 0),
  plafond   numeric(10,2) CHECK (plafond > 0),
  statut_extraction text NOT NULL CHECK (statut_extraction IN ('valide','non_exploitable')),
  violations        text[] NOT NULL DEFAULT '{}',
  modele text NOT NULL,
  version_prompt text NOT NULL
);

-- Cache d'analyse VLM : même fichier + même modèle + même prompt ⇒ même résultat
CREATE TABLE analyses (
  sha256 text REFERENCES blobs,
  modele text,
  version_prompt text,
  resultat jsonb NOT NULL,
  PRIMARY KEY (sha256, modele, version_prompt)
);

-- Snapshot de l'état partagé : claim check, jamais d'octets dans etat
CREATE TABLE demandes (
  reference      text PRIMARY KEY,
  numero_contrat text,
  etat           jsonb NOT NULL,
  etat_courant   text NOT NULL,
  statut         text NOT NULL
                 CHECK (statut IN ('admission','en_cours','terminee','secours')),
  maj            timestamptz NOT NULL DEFAULT now(),
  fiche          jsonb
);
CREATE INDEX demandes_reaper ON demandes (maj) WHERE statut = 'en_cours';

CREATE TABLE pieces (
  piece_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  reference      text NOT NULL REFERENCES demandes,
  sha256         text NOT NULL REFERENCES blobs,
  relance        int CHECK (relance >= 1),
  type           text NOT NULL CHECK (type IN ('facture','photo','depot_plainte')),
  statut_analyse text NOT NULL DEFAULT 'en_attente'
                 CHECK (statut_analyse IN ('en_attente','ok','echec')),
  lisible bool,
  montant numeric(10,2) CHECK (montant > 0),
  UNIQUE (reference, sha256)
);

-- Registre A2A : 1 appel par dossier (contrat §6)
CREATE TABLE appels_partenaire (
  reference text PRIMARY KEY REFERENCES demandes,
  reserve_le timestamptz NOT NULL DEFAULT now(),
  evaluation_id text
);

CREATE TABLE file_ingestion (
  id bigserial PRIMARY KEY,
  sha256 text NOT NULL REFERENCES blobs,
  tache  text NOT NULL CHECK (tache IN ('analyser_piece','extraire_contrat')),
  statut text NOT NULL DEFAULT 'en_attente'
         CHECK (statut IN ('en_attente','en_cours','faite','echec'))
);
CREATE INDEX file_a_traiter ON file_ingestion (id) WHERE statut = 'en_attente';
