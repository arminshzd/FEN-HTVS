#!/bin/sh
##SBATCH --job-name=acpype

# output file (including stderr)
#SBATCH --output=R_%x_%j.out

# email on start, end, and abortion
##SBATCH --mail-type=ALL
##SBATCH --mail-user=arminsh@uchicago.edu

# name of partition to queue on
##SBATCH --account=pi-andrewferguson
##SBATCH --partition=andrewferguson
#SBATCH --partition=gm4-pmext
#SBATCH --qos=gm4-cpu

# max wall time for job (HH:MM:SS)
#SBATCH --time=1-12:00:00

# number of nodes for this job
#SBATCH --nodes=1

# number of processes to run per node
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=20

# reserve the specified node(s) for this job
##SBATCH --exclusive

#module load python/anaconda-2022.05
module load python/anaconda-2021.05
source activate /project/andrewferguson/armin/envs/acpype

acpype -i $1.pdb -b PCC -c bcc -n $2 -a gaff2