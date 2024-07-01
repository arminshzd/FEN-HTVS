#!/bin/sh

# output file (including stderr)
#SBATCH --output=R_%x_%j.out

# name of partition to queue on
#SBATCH --partition=gm4-pmext
#SBATCH --qos=gm4

# max wall time for job (HH:MM:SS)
#SBATCH --time=1-12:00:00

# number of GPU(s) per node, if available
#SBATCH --gres=gpu:1

# number of nodes for this job
#SBATCH --nodes=1

# number of processes to run per node
#SBATCH --ntasks-per-node=5

# number of threads per cpu
#SBATCH --cpus-per-task=5

#SBATCH --exclusive

NCPU=$(($SLURM_NTASKS_PER_NODE))
NTHR=$(($SLURM_CPUS_PER_TASK))
NNOD=$(($SLURM_JOB_NUM_NODES))

NP=$(($NCPU * $NNOD * $NTHR))

module unload openmpi gcc cuda python
module load openmpi/4.1.1+gcc-10.1.0 cuda/11.2

source /project/andrewferguson/armin/grom_new/gromacs-2021.6/installed-files-mw2-256/bin/GMXRC

if [ -f ./md.cpt ]; then
    echo "Restarting previous run..."
    gmx mdrun -ntomp "$NP" -s md.tpr -cpi md.cpt -deffnm md -plumed plumed_restart.dat
else
    gmx grompp -f md.mdp -c ../npt/npt.gro -r ../npt/npt.gro -t ../npt/npt.cpt -p topol.top -o md.tpr
    gmx mdrun -ntomp "$NP" -deffnm md -plumed plumed.dat
fi
