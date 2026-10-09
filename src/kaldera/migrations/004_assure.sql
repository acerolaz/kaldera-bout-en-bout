-- Espace assuré (UI1). Écarts consignés au journal : demandes.cree_le (temps écoulé),
-- pieces.depose_le (ordre de dépôt : la dernière pièce d'un type fait foi), messages = événements.
ALTER TABLE demandes ADD COLUMN cree_le timestamptz NOT NULL DEFAULT now();
ALTER TABLE pieces ADD COLUMN depose_le timestamptz NOT NULL DEFAULT clock_timestamp();

CREATE TABLE utilisateurs (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  identifiant  text NOT NULL UNIQUE CHECK (length(identifiant) BETWEEN 3 AND 64),
  hash         text NOT NULL,
  role         text NOT NULL CHECK (role IN ('assure','admin')),
  echecs       int  NOT NULL DEFAULT 0,
  bloque_jusqu timestamptz
);

CREATE TABLE demandes_assure (
  utilisateur uuid NOT NULL REFERENCES utilisateurs ON DELETE CASCADE,
  reference   text NOT NULL REFERENCES demandes,
  PRIMARY KEY (utilisateur, reference)
);

-- Contenu déjà projeté (vue_assure) : rien d'interne n'y entre
CREATE TABLE evenements_assure (
  id        bigserial PRIMARY KEY,
  reference text NOT NULL REFERENCES demandes,
  type      text NOT NULL CHECK (type IN ('etape','piece','message','verdict')),
  etape     int CHECK (etape BETWEEN 1 AND 5),
  contenu   jsonb NOT NULL,
  cree_le   timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX evenements_par_demande ON evenements_assure (reference, id);
