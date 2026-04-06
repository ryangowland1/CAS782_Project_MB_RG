package queries;

public class scenegraphhelper {

    /**
     * Calculate the relative angle from source to target node.
     *
     * @param sourceX x coordinate of source node
     * @param sourceY y coordinate of source node
     * @param sourceHeading heading (in radians) of source node
     * @param targetX x coordinate of target node
     * @param targetY y coordinate of target node
     * @return angle in radians relative to source's heading
     *         angle > 0 = target is to the left
     *         angle < 0 = target is to the right
     */
    public static double calculateAngle(double sourceX, double sourceY, double sourceHeading,
                                       double targetX, double targetY) {
        double dx = targetX - sourceX;
        double dy = targetY - sourceY;
        double angleToTarget = Math.atan2(dy, dx);
        double relativeAngle = angleToTarget - sourceHeading;

        // Normalize to [-π, π]
        while (relativeAngle > Math.PI) {
            relativeAngle -= 2 * Math.PI;
        }
        while (relativeAngle < -Math.PI) {
            relativeAngle += 2 * Math.PI;
        }

        return relativeAngle;
    }

    public static boolean isVehicleInLane(double vehicleX, double vehicleY,
                                          double laneX, double laneY,
                                          double laneHeading, double laneLength,
                                          double laneWidth) {
        double dx = vehicleX - laneX;
        double dy = vehicleY - laneY;

        double cos = Math.cos(-laneHeading);
        double sin = Math.sin(-laneHeading);

        double longitudinal = dx * cos - dy * sin;
        double lateral = dx * sin + dy * cos;

        return Math.abs(longitudinal) <= laneLength / 2.0
            && Math.abs(lateral) <= laneWidth / 2.0;
    }

    // -----------------------------------------------------------------------
    // RSS safe-distance helpers (AV_Safety_Frameworks.pdf, Equations 1 & 3)
    // -----------------------------------------------------------------------

    // Default RSS parameters (representative values from the literature)
    private static final double RHO           = 0.5;   // reaction time (s)
    private static final double A_LON_MAX     = 3.5;   // max lon accel during reaction (m/s^2)
    private static final double B_LON_MIN     = 4.0;   // min ego braking decel (m/s^2)
    private static final double B_LON_MAX     = 8.0;   // max other braking decel (m/s^2)
    private static final double A_LAT_MAX     = 0.2;   // max lateral accel during reaction (m/s^2)
    private static final double B_LAT_MIN     = 0.8;   // min lateral braking decel (m/s^2)
    private static final double MU            = 0.1;   // lateral fluctuation margin (m)

    /**
     * RSS minimum safe longitudinal distance (Equation 1).
     *
     * @param vRear  longitudinal speed of rear (ego) vehicle (m/s, >= 0)
     * @param vFront longitudinal speed of front (lead) vehicle (m/s, >= 0)
     * @return minimum safe longitudinal gap (m)
     */
    public static double rssLongitudinalSafeDistance(double vRear, double vFront) {
        double vRRho = vRear + RHO * A_LON_MAX;
        double d = vRear * RHO
                 + 0.5 * A_LON_MAX * RHO * RHO
                 + (vRRho * vRRho) / (2.0 * B_LON_MIN)
                 - (vFront * vFront) / (2.0 * B_LON_MAX);
        return Math.max(0.0, d);
    }

    /**
     * RSS minimum safe lateral distance (Equation 3).
     *
     * @param vEgoToward  ego's lateral speed toward other (m/s, >= 0 means closing)
     * @param vOtherAway  other's lateral speed away from ego (m/s, >= 0 means opening)
     * @return minimum safe lateral gap (m)
     */
    public static double rssLateralSafeDistance(double vEgoToward, double vOtherAway) {
        double v1Rho = vEgoToward + RHO * A_LAT_MAX;
        double v2Rho = vOtherAway - RHO * A_LAT_MAX;

        double D1 = (vEgoToward + v1Rho) / 2.0 * RHO + (v1Rho * v1Rho) / (2.0 * B_LAT_MIN);
        double D2 = (vOtherAway + v2Rho) / 2.0 * RHO - (v2Rho * v2Rho) / (2.0 * B_LAT_MIN);

        return MU + Math.max(0.0, D1 - D2);
    }

    /**
     * Decompose one vehicle's velocity into another's longitudinal / lateral frame.
     *
     * @param heading   the reference heading (radians)
     * @param vx        world-frame X velocity component
     * @param vy        world-frame Y velocity component
     * @return [longitudinal, lateral] velocity in the frame defined by heading
     */
    public static double[] decomposeVelocity(double heading, double vx, double vy) {
        double fwdX  =  Math.cos(heading);
        double fwdY  =  Math.sin(heading);
        double perpX = -fwdY;
        double perpY =  fwdX;
        return new double[] {
            vx * fwdX  + vy * fwdY,   // longitudinal
            vx * perpX + vy * perpY   // lateral (positive = toward +perp side)
        };
    }

    /**
     * Check if the longitudinal gap between ego and a vehicle in front
     * violates the RSS safe distance.
     *
     * @param egoX, egoY      ego position
     * @param egoHeading      ego heading (radians)
     * @param egoVx, egoVy    ego world-frame velocity
     * @param otherX, otherY  other vehicle position
     * @param otherVx, otherVy other vehicle world-frame velocity
     * @param sameLaneThreshold max |lateral offset| to be in "same lane" (m)
     * @return true if the longitudinal safe distance is violated
     */
    public static boolean rssLongitudinalViolation(
            double egoX, double egoY, double egoHeading,
            double egoVx, double egoVy,
            double otherX, double otherY,
            double otherVx, double otherVy,
            double sameLaneThreshold) {

        double fwdX = Math.cos(egoHeading);
        double fwdY = Math.sin(egoHeading);
        double perpX = -fwdY;
        double perpY =  fwdX;

        double dx = otherX - egoX;
        double dy = otherY - egoY;
        double lonDist = dx * fwdX  + dy * fwdY;
        double latDist = dx * perpX + dy * perpY;

        // Only check vehicles in front, roughly same lane
        if (lonDist <= 0) return false;
        if (Math.abs(latDist) > sameLaneThreshold) return false;

        double egoLon  = egoVx * fwdX  + egoVy * fwdY;
        double otherLon = otherVx * fwdX + otherVy * fwdY;

        double dSafe = rssLongitudinalSafeDistance(
            Math.max(egoLon, 0.0), Math.max(otherLon, 0.0));

        return lonDist < dSafe;
    }

    /**
     * Check if the lateral gap between ego and a vehicle beside it
     * violates the RSS safe distance.
     *
     * @param egoX, egoY      ego position
     * @param egoHeading      ego heading (radians)
     * @param egoVx, egoVy    ego world-frame velocity
     * @param otherX, otherY  other vehicle position
     * @param otherVx, otherVy other vehicle world-frame velocity
     * @param lateralMinThreshold min |lateral offset| for "beside" (m)
     * @param lateralMaxThreshold max |lateral offset| for "beside" (m)
     * @param lonMaxThreshold max |longitudinal offset| for "beside" (m)
     * @return true if the lateral safe distance is violated
     */
    public static boolean rssLateralViolation(
            double egoX, double egoY, double egoHeading,
            double egoVx, double egoVy,
            double otherX, double otherY,
            double otherVx, double otherVy,
            double lateralMinThreshold,
            double lateralMaxThreshold,
            double lonMaxThreshold) {

        double fwdX = Math.cos(egoHeading);
        double fwdY = Math.sin(egoHeading);
        double perpX = -fwdY;
        double perpY =  fwdX;

        double dx = otherX - egoX;
        double dy = otherY - egoY;
        double lonDist = dx * fwdX  + dy * fwdY;
        double latDist = dx * perpX + dy * perpY;

        double absLat = Math.abs(latDist);

        // Only check vehicles beside ego
        if (absLat < lateralMinThreshold || absLat > lateralMaxThreshold) return false;
        if (Math.abs(lonDist) > lonMaxThreshold) return false;

        double egoLat  = egoVx * perpX  + egoVy * perpY;
        double otherLat = otherVx * perpX + otherVy * perpY;

        double vEgoToward, vOtherAway;
        if (latDist > 0) {
            // other is on +perp side
            vEgoToward = egoLat;
            vOtherAway = otherLat;
        } else {
            // other is on -perp side
            vEgoToward = -egoLat;
            vOtherAway = -otherLat;
        }

        double dSafe = rssLateralSafeDistance(vEgoToward, vOtherAway);
        return absLat < dSafe;
    }
}
